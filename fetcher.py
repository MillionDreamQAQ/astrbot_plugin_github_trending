"""GitHub Trending 数据获取层。

RSS 解析 + GitHub API 补全元数据 + 内存缓存。
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import feedparser

# ── RSS 源 ──────────────────────────────────────────────────────────────
RSS_DAILY = "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"
RSS_WEEKLY = "https://mshibanami.github.io/GitHubTrendingRSS/weekly/all.xml"

# GitHub API 模板
GITHUB_API_REPO = "https://api.github.com/repos/{owner}/{repo}"

# 语言 → 显示色（部分常用语言）
LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "C++": "#f34b7d",
    "C": "#555555",
    "C#": "#178600",
    "Ruby": "#701516",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "PHP": "#4F5D95",
    "Vue": "#41b883",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Jupyter Notebook": "#DA5B0B",
    "Dart": "#00B4AB",
    "Scala": "#c22d40",
    "Lua": "#000080",
    "R": "#198CE7",
    "Zig": "#ec915c",
    "Elixir": "#6e4a7e",
    "Haskell": "#5e5086",
    "Clojure": "#db5855",
}


@dataclass
class RepoInfo:
    """单个仓库的展示信息。"""

    rank: int
    owner: str
    repo: str
    url: str
    description: str = ""
    language: str = ""
    language_color: str = ""
    stars: int = 0
    stars_str: str = ""  # 格式化后的 star 数，如 "12.3k"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class TrendingFetcher:
    """GitHub Trending 数据获取器。

    1. 从 RSS feed 获取仓库列表
    2. 通过 GitHub API 批量补全 stars / language / description
    3. 内存缓存，避免短时间内重复请求
    """

    def __init__(self, github_token: str = ""):
        self._token = github_token
        self._cache: dict[str, tuple[list[RepoInfo], float]] = {}  # key → (data, timestamp)
        self._cache_ttl = 300  # 5 分钟缓存

    def _cache_key(self, feed_type: str) -> str:
        return f"trending_{feed_type}"

    def _get_cached(self, feed_type: str) -> Optional[list[RepoInfo]]:
        key = self._cache_key(feed_type)
        entry = self._cache.get(key)
        if entry:
            data, ts = entry
            if time.time() - ts < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, feed_type: str, data: list[RepoInfo]) -> None:
        self._cache[self._cache_key(feed_type)] = (data, time.time())

    # ── RSS 解析 ──────────────────────────────────────────────────────

    def _parse_rss(self, feed_type: str) -> list[dict]:
        """解析 RSS，返回原始条目列表。"""
        url = RSS_DAILY if feed_type == "daily" else RSS_WEEKLY
        feed = feedparser.parse(url)

        entries = []
        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()

            # title 格式: "owner/repo"
            if "/" not in title:
                continue

            owner, repo = title.split("/", 1)
            entries.append(
                {
                    "owner": owner.strip(),
                    "repo": repo.strip(),
                    "url": link,
                }
            )

        return entries

    # ── GitHub API ─────────────────────────────────────────────────────

    async def _enrich_repo(
        self,
        session: aiohttp.ClientSession,
        sem: asyncio.Semaphore,
        owner: str,
        repo: str,
    ) -> dict:
        """通过 GitHub API 获取单个仓库的 stars / language / description。"""
        url = GITHUB_API_REPO.format(owner=owner, repo=repo)
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"

        result = {"stars": 0, "language": "", "description": ""}

        async with sem:
            try:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result["stars"] = data.get("stargazers_count", 0)
                        result["language"] = data.get("language") or ""
                        result["description"] = (data.get("description") or "").strip()
                    elif resp.status == 403:
                        # 速率限制
                        result["description"] = "[API rate limited]"
                    elif resp.status == 404:
                        result["description"] = "[Repo not found]"
            except (aiohttp.ClientError, asyncio.TimeoutError):
                result["description"] = "[Network error]"

        return result

    async def _enrich_all(
        self, session: aiohttp.ClientSession, entries: list[dict]
    ) -> None:
        """并发补全所有仓库的元数据。"""
        sem = asyncio.Semaphore(5)  # 并发上限，避免触发限流

        tasks = [
            self._enrich_repo(session, sem, e["owner"], e["repo"]) for e in entries
        ]
        results = await asyncio.gather(*tasks)

        for entry, result in zip(entries, results):
            entry.update(result)

    # ── 格式化 ─────────────────────────────────────────────────────────

    @staticmethod
    def _format_stars(count: int) -> str:
        """将 star 数格式化为人类可读形式。"""
        if count >= 1000:
            k = count / 1000
            if k >= 100:
                return f"{int(k)}k"
            return f"{k:.1f}k"
        return str(count)

    @staticmethod
    def _format_description(desc: str, max_len: int = 80) -> str:
        """截断过长的描述。"""
        desc = desc.strip()
        if len(desc) > max_len:
            return desc[: max_len - 3] + "..."
        return desc

    # ── 公开接口 ───────────────────────────────────────────────────────

    async def fetch(self, feed_type: str = "daily") -> list[RepoInfo]:
        """获取 trending 数据（优先缓存）。

        Args:
            feed_type: "daily" 或 "weekly"

        Returns:
            RepoInfo 列表，按 RSS 原始顺序排列。
        """
        # 查缓存
        cached = self._get_cached(feed_type)
        if cached is not None:
            return cached

        # 解析 RSS
        entries = self._parse_rss(feed_type)
        if not entries:
            raise RuntimeError(
                f"RSS feed returned no entries for {feed_type}. "
                f"URL: {RSS_DAILY if feed_type == 'daily' else RSS_WEEKLY}"
            )

        # 通过 GitHub API 补全
        async with aiohttp.ClientSession() as session:
            await self._enrich_all(session, entries)

        # 构造 RepoInfo 列表
        repos: list[RepoInfo] = []
        for i, entry in enumerate(entries):
            stars = entry.get("stars", 0)
            language = entry.get("language", "")
            description = self._format_description(entry.get("description", ""))

            repos.append(
                RepoInfo(
                    rank=i + 1,
                    owner=entry["owner"],
                    repo=entry["repo"],
                    url=entry["url"],
                    description=description,
                    language=language,
                    language_color=LANGUAGE_COLORS.get(language, "#8b8b8b"),
                    stars=stars,
                    stars_str=self._format_stars(stars),
                )
            )

        # 写缓存
        self._set_cache(feed_type, repos)
        return repos

    def clear_cache(self) -> None:
        """清除所有缓存。"""
        self._cache.clear()
