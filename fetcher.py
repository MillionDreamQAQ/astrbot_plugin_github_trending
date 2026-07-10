"""GitHub Trending 数据获取层。

直接抓取 GitHub Trending 页面 (https://github.com/trending)，
用 BeautifulSoup 解析 HTML，提取仓库排名、名称、描述、语言、Star 数等信息。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

# ── Trending 页面 URL ────────────────────────────────────────────────────
TRENDING_URL = "https://github.com/trending"

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
    "MDX": "#fcb32c",
    "SCSS": "#c6538c",
    "Dockerfile": "#384d54",
    "Makefile": "#427819",
    "CMake": "#DA3434",
    "Objective-C": "#438eff",
    "Blade": "#f7523f",
    "Astro": "#ff5a03",
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
    stars_str: str = ""
    stars_today: int = 0
    stars_today_str: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class TrendingFetcher:
    """GitHub Trending 数据获取器。

    直接抓取 GitHub Trending 页面并解析 HTML，一个请求拿到所有数据。
    """

    def __init__(self, github_token: str = "", translator=None):
        self._token = github_token
        self._translator = translator
        self._cache: dict[str, tuple[list[RepoInfo], float]] = {}
        self._cache_ttl = 300  # 5 分钟缓存

    # ── 缓存 ─────────────────────────────────────────────────────────────

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

    def clear_cache(self) -> None:
        self._cache.clear()

    # ── 格式化工具 ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_int(text: str) -> int:
        """解析 "2,194" 或 "76,258" 格式的数字。"""
        return int(text.replace(",", "").strip())

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

    # ── HTML 抓取 & 解析 ──────────────────────────────────────────────────

    async def _fetch_html(self, feed_type: str) -> str:
        """获取 GitHub Trending 页面 HTML。"""
        since = "daily" if feed_type == "daily" else "weekly"
        url = f"{TRENDING_URL}?since={since}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        if self._token:
            headers["Authorization"] = f"token {self._token}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"GitHub Trending 返回 HTTP {resp.status}"
                    )
                return await resp.text()

    def _parse_html(self, html: str) -> list[RepoInfo]:
        """解析 GitHub Trending 页面 HTML，提取仓库列表。"""
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article", class_="Box-row")

        repos: list[RepoInfo] = []
        rank = 0

        for article in articles:
            rank += 1

            # ── 仓库名称 ──────────────────────────────────────────────
            h2 = article.find("h2", class_=re.compile(r"h3|lh-condensed"))
            name_link = h2.find("a", class_="Link") if h2 else None
            if not name_link:
                continue

            href = name_link.get("href", "").strip()
            # href 格式: "/owner/repo"
            parts = href.strip("/").split("/")
            if len(parts) < 2:
                continue
            owner, repo = parts[0], parts[1]

            # 清理 repo 名（可能含多余空白）
            repo = repo.strip()

            # ── 描述 ──────────────────────────────────────────────────
            desc_el = article.find("p", class_=re.compile(r"col-9|color-fg-muted|my-1"))
            description = desc_el.get_text(strip=True) if desc_el else ""

            # ── 语言 ──────────────────────────────────────────────────
            lang_color_el = article.find("span", class_="repo-language-color")
            language = ""
            language_color = ""
            if lang_color_el:
                style = lang_color_el.get("style", "")
                color_match = re.search(r"#([0-9a-fA-F]{6})", style)
                if color_match:
                    language_color = f"#{color_match.group(1)}"
                # 语言名在相邻的 span 中
                lang_name_el = article.find("span", itemprop="programmingLanguage")
                if lang_name_el:
                    language = lang_name_el.get_text(strip=True)

            # ── 总 Star 数 ────────────────────────────────────────────
            stars_link = article.find("a", href=re.compile(r"/stargazers$"))
            stars = 0
            if stars_link:
                stars_text = stars_link.get_text(strip=True)
                # 提取数字部分
                stars_match = re.search(r"[\d,]+", stars_text)
                if stars_match:
                    stars = self._parse_int(stars_match.group())

            # ── 今日 Star 数 ──────────────────────────────────────────
            stars_today = 0
            today_el = article.find("span", class_="float-sm-right")
            if today_el:
                today_text = today_el.get_text(strip=True)
                today_match = re.search(r"([\d,]+)\s*stars?\s*today", today_text)
                if today_match:
                    stars_today = self._parse_int(today_match.group(1))

            # ── 构造 RepoInfo ─────────────────────────────────────────
            repos.append(
                RepoInfo(
                    rank=rank,
                    owner=owner,
                    repo=repo,
                    url=f"https://github.com/{owner}/{repo}",
                    description=self._format_description(description),
                    language=language,
                    language_color=LANGUAGE_COLORS.get(language, language_color),
                    stars=stars,
                    stars_str=self._format_stars(stars),
                    stars_today=stars_today,
                    stars_today_str=self._format_stars(stars_today) if stars_today > 0 else "",
                )
            )

        return repos

    async def _translate_descriptions(self, repos: list[RepoInfo]):
        """批量翻译仓库描述。翻译结果直接替换原描述字段。"""
        # 收集需要翻译的描述（跳过空字符串和已缓存项）
        texts = [r.description for r in repos if r.description]
        if not texts:
            return

        try:
            translated = await self._translator.translate_batch(texts)
        except Exception:
            return  # 翻译失败静默降级，保留原文

        # 替换
        idx = 0
        for repo in repos:
            if repo.description:
                if idx < len(translated):
                    repo.description = translated[idx]
                idx += 1

    # ── 公开接口 ──────────────────────────────────────────────────────────

    async def fetch(self, feed_type: str = "daily") -> list[RepoInfo]:
        """获取 trending 数据（优先缓存）。

        Args:
            feed_type: "daily" 或 "weekly"

        Returns:
            RepoInfo 列表，按排名顺序排列。
        """
        # 查缓存
        cached = self._get_cached(feed_type)
        if cached is not None:
            return cached

        # 抓取页面
        html = await self._fetch_html(feed_type)

        # 解析 HTML
        repos = self._parse_html(html)

        # 翻译描述（如果配置了翻译器）
        if self._translator and repos:
            await self._translate_descriptions(repos)

        if not repos:
            raise RuntimeError(
                f"未能从 GitHub Trending 页面解析到任何仓库（{feed_type}）。"
            )

        # 写缓存
        self._set_cache(feed_type, repos)
        return repos
