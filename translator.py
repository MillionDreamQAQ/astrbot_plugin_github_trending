"""翻译模块 — 通过 Google Translate 免费接口批量翻译文本。

使用 aiohttp 直接请求 translate.googleapis.com，无需 API Key。
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import aiohttp

# Google Translate 免费接口
_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
# 单次请求最大字符数（Google 限制约 5000 字符）
_MAX_CHUNK_SIZE = 4000


class Translator:
    """轻量级翻译器，内置缓存避免重复请求。"""

    def __init__(self, source: str = "en", target: str = "zh-CN"):
        self.source = source
        self.target = target
        self._cache: dict[str, str] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _cache_key(self, text: str) -> str:
        return f"{self.source}|{self.target}|{text}"

    def get_cached(self, text: str) -> Optional[str]:
        return self._cache.get(self._cache_key(text))

    # ── 公开接口 ──────────────────────────────────────────────────────────

    async def translate(self, text: str) -> str:
        """翻译单段文本。空文本或纯数字/符号直接返回原文。"""
        text = text.strip()
        if not text:
            return text

        # 纯数字/符号/链接不翻译
        if re.match(r"^[\d\s.,;:!?@#\$%^&*()\[\]{}/\\<>|\-_+=~`'\"➕→←↑↓✓✗•·©®™]+$", text):
            return text

        # 查缓存
        cached = self.get_cached(text)
        if cached is not None:
            return cached

        await self._ensure_session()

        params = {
            "client": "gtx",
            "sl": self.source,
            "tl": self.target,
            "dt": "t",
            "q": text,
        }

        try:
            async with self._session.get(
                _TRANSLATE_URL, params=params, timeout=10
            ) as resp:
                if resp.status == 429:
                    # 被限流，等一秒重试一次
                    await asyncio.sleep(1)
                    async with self._session.get(
                        _TRANSLATE_URL, params=params, timeout=10
                    ) as resp2:
                        if resp2.status != 200:
                            return text  # 失败返回原文
                        data = await resp2.json()
                elif resp.status != 200:
                    return text
                else:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return text  # 网络错误返回原文

        # 解析结果: [[["译文", "原文", ...], ...], ...]
        try:
            parts = []
            for segment in data[0]:
                if segment[0]:
                    parts.append(segment[0])
            result = " ".join(parts).strip()
        except (IndexError, KeyError, TypeError):
            return text

        if not result:
            return text

        # 写缓存
        self._cache[self._cache_key(text)] = result
        return result

    async def translate_batch(self, texts: list[str]) -> list[str]:
        """批量翻译，自动分批 + 间隔避免限流。"""
        if not texts:
            return []

        results: list[str] = []
        chunk: list[str] = []
        chunk_len = 0

        for text in texts:
            # 跳过空文本和已缓存的
            if not text.strip():
                continue
            if self.get_cached(text):
                continue

            if chunk_len + len(text) > _MAX_CHUNK_SIZE:
                # 翻译当前批次
                await self._translate_chunk(chunk)
                chunk = []
                chunk_len = 0
                await asyncio.sleep(0.3)  # 批次间短暂间隔

            chunk.append(text)
            chunk_len += len(text)

        # 翻译最后一批
        if chunk:
            await self._translate_chunk(chunk)

        # 组装结果（从缓存读取）
        for text in texts:
            translated = self.get_cached(text)
            results.append(translated if translated else text)

        return results

    async def _translate_chunk(self, texts: list[str]):
        """翻译一批文本（用换行符拼接，减少请求数）。"""
        if not texts:
            return
        # 用 ||| 分隔，避免翻译后无法拆分
        joined = "\n|||\n".join(texts)
        translated = await self.translate(joined)

        # 按分隔符拆分
        parts = [p.strip() for p in translated.split("|||")]
        # 如果拆分数量不匹配，放弃这批翻译（缓存不写）
        if len(parts) == len(texts):
            for original, translated_part in zip(texts, parts):
                key = self._cache_key(original)
                self._cache[key] = translated_part
        else:
            # 回退：逐个翻译
            for text in texts:
                await self.translate(text)
                await asyncio.sleep(0.2)
