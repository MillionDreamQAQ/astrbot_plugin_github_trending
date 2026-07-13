"""GitHub Trending AstrBot 插件。

功能：
- /trending — 手动获取每日 GitHub Trending 榜单
- /trending weekly — 获取本周榜单
- /trending addhere — 创建订阅（可选参数：时间 语言 社区）
- /trending delhere [id] — 删除订阅
- /trending list — 查看所有订阅
- /trending sub <id> ... — 管理订阅（enable/disable/time/language/community）
- /trending time/language/community — 设置默认值（影响手动 /trending 和 addhere）
- /trending lang/proxy/token/debug/status/help

定时任务：每分钟轮询，为每个到达推送时间的订阅独立拉取并推送。
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import datetime, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

try:
    from .fetcher import TrendingFetcher
    from .renderer import render_trending
    from .translator import Translator
except ImportError:
    from fetcher import TrendingFetcher
    from renderer import render_trending
    from translator import Translator


# ── 默认配置 ────────────────────────────────────────────────────────────
DEFAULT_CONFIG: dict = {
    "subscriptions": [],  # [{"id","umo","type","push_time","language","spoken_language","enabled"}]
    "push_time": "09:00",        # addhere / 手动 trending 的默认时间
    "language": "",              # addhere / 手动 trending 的默认编程语言
    "spoken_language": "",       # addhere / 手动 trending 的默认社区
    "github_token": "",
    "translate_enabled": True,
    "proxy": "",
}

PLUGIN_NAME = "astrbot_plugin_github_trending"


@register(PLUGIN_NAME, "MillionDream", "每日 GitHub Trending 榜单推送插件", "1.1.0")
class GitHubTrendingPlugin(Star):
    """GitHub Trending 插件主类。"""

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self._config: dict = {**DEFAULT_CONFIG, **(config or {})}
        proxy = self._config.get("proxy", "")
        self._translator: Translator | None = None
        self._init_translator()
        self._fetcher = TrendingFetcher(
            github_token=self._config.get("github_token", ""),
            translator=self._translator,
            proxy=proxy,
        )
        self._scheduler_task: asyncio.Task | None = None
        self._running = False
        # 推送防重：{sub_id: last_push_date_str}
        self._pushed_today: dict[str, str] = {}

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _sync_proxy(self):
        proxy = self._config.get("proxy", "")
        self._fetcher._proxy = proxy
        if hasattr(self._fetcher, "clear_cache"):
            self._fetcher.clear_cache()
        if self._translator:
            self._translator._proxy = proxy

    def _get_lang_args(self, sub: dict | None = None) -> dict:
        """获取语言过滤参数。传入 subscription 则用它的设置，否则用全局默认。"""
        if sub:
            return {
                "language": sub.get("language", ""),
                "spoken_language": sub.get("spoken_language", ""),
            }
        return {
            "language": self._config.get("language", ""),
            "spoken_language": self._config.get("spoken_language", ""),
        }

    def _init_translator(self):
        proxy = self._config.get("proxy", "")
        if self._config.get("translate_enabled", True):
            if self._translator is None:
                self._translator = Translator(source="en", target="zh-CN", proxy=proxy)
        else:
            if self._translator:
                self._translator = None
        if hasattr(self, "_fetcher"):
            self._fetcher._translator = self._translator
            self._fetcher.clear_cache()

    # ── 迁移 ──────────────────────────────────────────────────────────────

    def _migrate_config(self):
        """自动迁移旧配置：targets[] → subscriptions[]。"""
        old_targets = self._config.get("targets", [])
        if not old_targets:
            return  # 无旧数据，无需迁移

        old_time = self._config.pop("push_time", "09:00")
        old_lang = self._config.pop("language", "")
        old_sl = self._config.pop("spoken_language", "")
        subs = self._config.get("subscriptions", [])

        for t in old_targets:
            sub = {
                "id": str(uuid.uuid4())[:8],
                "umo": t.get("umo", ""),
                "type": t.get("type", "group"),
                "push_time": old_time,
                "language": old_lang,
                "spoken_language": old_sl,
                "enabled": True,
            }
            subs.append(sub)

        self._config["subscriptions"] = subs
        del self._config["targets"]
        logger.info(f"[GitHubTrending] 已迁移 {len(old_targets)} 个旧目标到订阅系统")

    # ── 生命周期 ──────────────────────────────────────────────────────────

    async def initialize(self):
        await self._load_config()
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        subs = self._config.get("subscriptions", [])
        unique_times = sorted(set(s.get("push_time", "09:00") for s in subs if s.get("enabled", True)))
        logger.info(
            f"[GitHubTrending] 插件已启动，{len(subs)} 个订阅，"
            f"推送时间: {', '.join(unique_times) if unique_times else '无'}"
        )

    async def terminate(self):
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("[GitHubTrending] 插件已停止")

    # ── 配置持久化 ────────────────────────────────────────────────────────

    async def _load_config(self):
        saved = await self.get_kv_data("config", None)
        if saved:
            self._config.update(saved)
        self._migrate_config()
        self._init_translator()
        self._sync_proxy()
        token = self._config.get("github_token", "")
        if token:
            self._fetcher._token = token

    async def _save_config(self):
        await self.put_kv_data("config", self._config)

    # ── 定时任务（每分钟轮询）────────────────────────────────────────────

    async def _scheduler_loop(self):
        """每分钟轮询，为到达推送时间的订阅执行推送。"""
        while self._running:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                today_str = now.strftime("%Y-%m-%d")

                for sub in self._config.get("subscriptions", []):
                    if not sub.get("enabled", True):
                        continue
                    if sub.get("push_time", "09:00") != current_time:
                        continue
                    # 防重：今天已推送过则跳过
                    if self._pushed_today.get(sub["id"]) == today_str:
                        continue

                    # 异步执行推送
                    asyncio.create_task(self._push_subscription(sub))

                # 清理过期的防重记录
                stale = [k for k, v in self._pushed_today.items() if v != today_str]
                for k in stale:
                    del self._pushed_today[k]

                # 等到下一分钟
                await asyncio.sleep(60 - now.second)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[GitHubTrending] 调度器异常")
                await asyncio.sleep(60)

    async def _push_subscription(self, sub: dict):
        """为单个订阅拉取数据并推送。"""
        sub_id = sub.get("id", "?")
        umo = sub.get("umo", "")
        today_str = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[GitHubTrending] 推送订阅 {sub_id} → {umo} (lang={sub.get('language') or 'all'}, community={sub.get('spoken_language') or 'all'})")

        try:
            repos = await self._fetcher.fetch("daily", **self._get_lang_args(sub))
            image_bytes = render_trending(repos, "daily")
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            links_text = self._build_links_text(repos, "daily")
            await self._send_to(umo, b64, "daily", links_text)
            self._pushed_today[sub_id] = today_str
            logger.info(f"[GitHubTrending] 订阅 {sub_id} 推送完成，{len(repos)} 个项目")
        except Exception:
            self._pushed_today[sub_id] = today_str  # 标记已尝试，避免反复重试
            logger.exception(f"[GitHubTrending] 订阅 {sub_id} 推送失败")

    async def _send_to(self, umo: str, b64_image: str, feed_type: str, links_text: str = ""):
        """发送图片+链接到指定 UMO。"""
        from astrbot.core.message.message_event_result import MessageChain

        title = "GitHub Trending Daily" if feed_type == "daily" else "GitHub Trending Weekly"
        chain = MessageChain()
        chain.chain = [Plain(f"🔥 {title}\n"), Image.fromBase64(b64_image)]
        if links_text:
            chain.chain.append(Plain(f"\n{links_text}"))
        await self.context.send_message(umo, chain)

    # ── 手动触发 ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_links_text(repos: list, feed_type: str) -> str:
        trending_url = (
            "https://github.com/trending?since=daily"
            if feed_type == "daily"
            else "https://github.com/trending?since=weekly"
        )
        lines = [f"🔗 完整榜单: {trending_url}", ""]
        top_n = min(5, len(repos))
        if top_n > 0:
            lines.append(f"📌 热门项目直达 (Top {top_n}):")
            for repo in repos[:top_n]:
                lines.append(f"  {repo.rank}. {repo.full_name}")
                lines.append(f"     {repo.url}")
                if repo.description:
                    lines.append(f"     {repo.description[:60]}")
        return "\n".join(lines)

    async def _fetch_and_send(self, event: AstrMessageEvent, feed_type: str):
        yield event.plain_result(f"🔍 正在获取 GitHub Trending {feed_type} 榜单...")
        try:
            repos = await self._fetcher.fetch(feed_type, **self._get_lang_args())
        except Exception as e:
            logger.exception(f"[GitHubTrending] 获取榜单失败 ({feed_type})")
            yield event.plain_result(f"❌ 获取榜单失败: {e}")
            return
        if not repos:
            yield event.plain_result("⚠️ 未能获取到任何项目，请稍后重试。")
            return
        try:
            image_bytes = render_trending(repos, feed_type)
        except Exception as e:
            logger.exception("[GitHubTrending] 图片渲染失败")
            yield event.plain_result(f"❌ 图片渲染失败: {e}")
            return
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        chain = [Image.fromBase64(b64)]
        yield event.chain_result(chain)
        yield event.plain_result(self._build_links_text(repos, feed_type))

    # ── 订阅管理 ──────────────────────────────────────────────────────────

    def _sub_by_id(self, sub_id: str) -> dict | None:
        for s in self._config.get("subscriptions", []):
            if s.get("id") == sub_id:
                return s
        return None

    @staticmethod
    def _format_sub(sub: dict, idx: int = 0) -> str:
        sid = sub.get("id", "?")
        ttype = "群聊" if sub.get("type") == "group" else "私聊"
        enabled = "✅" if sub.get("enabled", True) else "❌"
        pl = sub.get("language") or "全语言"
        sl = sub.get("spoken_language") or "不限"
        time_str = sub.get("push_time", "09:00")
        num = f"#{idx} " if idx else ""
        return (
            f"  {num}[{enabled}] {sid} | {ttype}\n"
            f"      ⏰ {time_str}  📂 {pl}  🌍 {sl}"
        )

    # 已知社区代码（2 字母），用于 addhere 时区分 language 和 community
    _COMMUNITY_CODES = {
        "zh", "ja", "ko", "fr", "de", "es", "pt", "ru", "en",
        "ar", "hi", "it", "nl", "pl", "sv", "tr", "vi",
    }

    async def _add_subscription(self, event: AstrMessageEvent, args: str):
        """创建订阅：/trending addhere [time] [language] [community]

        参数顺序任意，自动识别：
        - 含 ":" 的 → 推送时间
        - 2 字母且在已知社区代码中 → 社区
        - 其他 → 编程语言
        """
        umo = event.unified_msg_origin
        if not umo:
            yield event.plain_result("❌ 无法获取当前会话标识。")
            return

        ttype = "group" if "group" in umo.lower() else "user"

        # 解析参数
        push_time = self._config.get("push_time", "09:00")
        language = self._config.get("language", "")
        community = self._config.get("spoken_language", "")

        for part in args.split():
            if ":" in part:
                push_time = part
            elif len(part) == 2 and part.lower() in self._COMMUNITY_CODES:
                community = part.lower()
            else:
                language = part.lower()

        sub = {
            "id": str(uuid.uuid4())[:8],
            "umo": umo,
            "type": ttype,
            "push_time": push_time,
            "language": language,
            "spoken_language": community,
            "enabled": True,
        }
        self._config.setdefault("subscriptions", []).append(sub)
        await self._save_config()
        yield event.plain_result(
            f"✅ 订阅已创建！\n{self._format_sub(sub)}\n"
            f"使用 /trending sub {sub['id']} ... 可修改设置"
        )

    async def _del_subscription(self, event: AstrMessageEvent, args: str):
        """删除订阅：/trending delhere [id]"""
        umo = event.unified_msg_origin
        subs = self._config.get("subscriptions", [])
        sub_id = args.strip()

        if sub_id:
            # 按 ID 删除
            sub = self._sub_by_id(sub_id)
            if not sub:
                yield event.plain_result(f"❌ 未找到订阅: {sub_id}")
                return
            if sub.get("umo") != umo:
                yield event.plain_result(f"❌ 订阅 {sub_id} 不属于当前会话。")
                return
            self._config["subscriptions"] = [s for s in subs if s.get("id") != sub_id]
            await self._save_config()
            yield event.plain_result(f"✅ 已删除订阅 {sub_id}。")
        else:
            # 删除当前会话的所有订阅
            mine = [s for s in subs if s.get("umo") == umo]
            if not mine:
                yield event.plain_result("ℹ️ 当前会话没有订阅。")
                return
            self._config["subscriptions"] = [s for s in subs if s.get("umo") != umo]
            await self._save_config()
            yield event.plain_result(f"✅ 已删除当前会话的全部 {len(mine)} 个订阅。")

    async def _list_subscriptions(self, event: AstrMessageEvent):
        """列出所有订阅。"""
        subs = self._config.get("subscriptions", [])
        if not subs:
            yield event.plain_result("📭 当前没有订阅。\n使用 /trending addhere 创建。")
            return

        lines = [f"📋 订阅列表 (共 {len(subs)} 个):\n"]
        for i, s in enumerate(subs, 1):
            lines.append(self._format_sub(s, i))
            lines.append(f"      UMO: {s.get('umo', '?')}")
        lines.append(f"\n💡 /trending sub <id> ...  管理订阅")
        lines.append(f"💡 /trending addhere [time] [lang] [community]  创建订阅")

        yield event.plain_result("\n".join(lines))

    async def _manage_subscription(self, event: AstrMessageEvent, args: str):
        """管理订阅：/trending sub <id> <action> [value]"""
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            yield event.plain_result(
                "⚠️ 用法: /trending sub <id> <操作> [值]\n"
                "操作: enable / disable / time HH:MM / language LANG / community CODE\n"
                "示例: /trending sub abc123 time 18:00\n"
                "示例: /trending sub abc123 language python\n"
                "示例: /trending sub abc123 community zh\n"
                "示例: /trending sub abc123 disable"
            )
            return

        sub_id, action = parts[0], parts[1].lower()
        value = parts[2] if len(parts) > 2 else ""

        sub = self._sub_by_id(sub_id)
        if not sub:
            yield event.plain_result(f"❌ 未找到订阅: {sub_id}")
            return

        if action == "enable":
            sub["enabled"] = True
            await self._save_config()
            yield event.plain_result(f"✅ 订阅 {sub_id} 已启用。")
        elif action == "disable":
            sub["enabled"] = False
            await self._save_config()
            yield event.plain_result(f"✅ 订阅 {sub_id} 已禁用。")
        elif action == "time":
            if not value or ":" not in value:
                yield event.plain_result("⚠️ 格式: /trending sub <id> time HH:MM")
                return
            sub["push_time"] = value
            await self._save_config()
            yield event.plain_result(f"✅ 订阅 {sub_id} 推送时间已改为 {value}。")
        elif action == "language":
            sub["language"] = value.lower() if value else ""
            self._fetcher.clear_cache()
            await self._save_config()
            lang = value or "全语言"
            yield event.plain_result(f"✅ 订阅 {sub_id} 编程语言已改为 {lang}。")
        elif action == "community":
            sub["spoken_language"] = value.lower() if value else ""
            self._fetcher.clear_cache()
            await self._save_config()
            sl = value or "不限"
            yield event.plain_result(f"✅ 订阅 {sub_id} 社区已改为 {sl}。")
        else:
            yield event.plain_result(f"⚠️ 未知操作: {action}。支持: enable/disable/time/language/community")

    # ── 指令分发 ──────────────────────────────────────────────────────────

    @filter.command("trending")
    async def trending(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        parts = msg.split(maxsplit=1)
        subcmd_and_args = parts[1] if len(parts) > 1 else ""
        sub_parts = subcmd_and_args.split(maxsplit=1)
        subcmd = sub_parts[0].lower() if sub_parts else ""
        arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""

        if subcmd in ("", "daily"):
            async for r in self._fetch_and_send(event, "daily"):
                yield r
        elif subcmd in ("help", "h"):
            async for r in self._show_help(event):
                yield r
        elif subcmd == "weekly":
            async for r in self._fetch_and_send(event, "weekly"):
                yield r
        elif subcmd == "addhere":
            async for r in self._add_subscription(event, arg):
                yield r
        elif subcmd == "delhere":
            async for r in self._del_subscription(event, arg):
                yield r
        elif subcmd == "list":
            async for r in self._list_subscriptions(event):
                yield r
        elif subcmd == "sub":
            async for r in self._manage_subscription(event, arg):
                yield r
        elif subcmd == "time":
            async for r in self._set_time(event, arg):
                yield r
        elif subcmd == "token":
            async for r in self._set_token(event, arg):
                yield r
        elif subcmd == "lang":
            async for r in self._toggle_lang(event, arg):
                yield r
        elif subcmd == "proxy":
            async for r in self._set_proxy(event, arg):
                yield r
        elif subcmd == "language":
            async for r in self._set_language(event, arg):
                yield r
        elif subcmd == "community":
            async for r in self._set_community(event, arg):
                yield r
        elif subcmd == "debug":
            async for r in self._run_diagnostics(event):
                yield r
        elif subcmd == "status":
            async for r in self._show_status(event):
                yield r
        else:
            yield event.plain_result(
                f"⚠️ 未知子命令: {subcmd}\n"
                "可用子命令: weekly, addhere, delhere, list, sub, time, lang, proxy, language, community, token, debug, status, help"
            )

    # ── 子命令实现 ────────────────────────────────────────────────────────

    async def _show_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "🔥 GitHub Trending 插件\n"
            "─────────────────────\n"
            "/trending                 获取今日榜单\n"
            "/trending weekly          获取本周榜单\n"
            "/trending addhere [time/language/community]  创建订阅（参数顺序任意）\n"
            "/trending delhere [id]    删除订阅（无id=全部）\n"
            "/trending list            查看所有订阅\n"
            "/trending sub <id> <操作> 管理订阅\n"
            "  操作: enable / disable / time HH:MM / language LANG / community CODE\n"
            "/trending time HH:MM      设置默认推送时间\n"
            "/trending language LANG   设置默认编程语言\n"
            "/trending community CODE  设置默认社区\n"
            "/trending lang on/off     开关中文翻译\n"
            "/trending proxy URL       设置代理\n"
            "/trending token ghp_xxx   设置 GitHub Token\n"
            "/trending debug           诊断网络/解析/翻译\n"
            "/trending status          查看完整配置\n"
            "/trending help            显示此帮助"
        )

    async def _set_time(self, event: AstrMessageEvent, arg: str):
        if not arg:
            yield event.plain_result("⚠️ 请指定时间: /trending time HH:MM")
            return
        try:
            h, m = map(int, arg.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, TypeError):
            yield event.plain_result("⚠️ 时间格式无效。")
            return
        self._config["push_time"] = arg
        await self._save_config()
        yield event.plain_result(f"✅ 默认推送时间已设为 {arg}（新创建的订阅将使用此时间）")

    async def _set_token(self, event: AstrMessageEvent, arg: str):
        if not arg:
            yield event.plain_result("⚠️ 请提供 GitHub Token: /trending token ghp_xxx")
            return
        token = arg.strip()
        self._config["github_token"] = token
        self._fetcher._token = token
        self._fetcher.clear_cache()
        await self._save_config()
        yield event.plain_result(f"✅ GitHub Token 已设置。")

    async def _toggle_lang(self, event: AstrMessageEvent, arg: str):
        enabled = self._config.get("translate_enabled", True)
        if arg and arg.lower() == "off":
            self._config["translate_enabled"] = False
            self._init_translator()
            await self._save_config()
            yield event.plain_result("✅ 翻译已关闭。")
        elif arg and arg.lower() == "on":
            self._config["translate_enabled"] = True
            self._init_translator()
            await self._save_config()
            yield event.plain_result("✅ 翻译已开启。")
        else:
            state = "开启 ✅" if enabled else "关闭 ❌"
            yield event.plain_result(f"翻译: {state}\n用法: /trending lang on/off")

    async def _set_proxy(self, event: AstrMessageEvent, arg: str):
        if not arg or arg.lower() == "none":
            self._config["proxy"] = ""
            self._sync_proxy()
            await self._save_config()
            yield event.plain_result("✅ 代理已清除。")
        else:
            proxy = arg.strip()
            if not any(proxy.startswith(p) for p in ("http://", "https://", "socks5://")):
                yield event.plain_result("⚠️ 格式无效，请使用 http://host:port 或 socks5://host:port")
                return
            self._config["proxy"] = proxy
            self._sync_proxy()
            await self._save_config()
            yield event.plain_result(f"✅ 代理已设置: {proxy}")

    async def _set_language(self, event: AstrMessageEvent, arg: str):
        if not arg or arg.lower() == "all":
            self._config["language"] = ""
            self._fetcher.clear_cache()
            await self._save_config()
            yield event.plain_result("✅ 默认编程语言已清除（全语言）。")
        else:
            lang = arg.strip().lower()
            self._config["language"] = lang
            self._fetcher.clear_cache()
            await self._save_config()
            yield event.plain_result(f"✅ 默认编程语言已设: {lang}")

    async def _set_community(self, event: AstrMessageEvent, arg: str):
        code_map = {"zh": "中文", "ja": "日文", "ko": "韩文", "fr": "法文",
                     "de": "德文", "es": "西班牙文", "pt": "葡萄牙文", "ru": "俄文"}
        if not arg or arg.lower() == "all":
            self._config["spoken_language"] = ""
            self._fetcher.clear_cache()
            await self._save_config()
            yield event.plain_result("✅ 默认社区已清除（不限）。")
        else:
            code = arg.strip().lower()
            label = code_map.get(code, code)
            self._config["spoken_language"] = code
            self._fetcher.clear_cache()
            await self._save_config()
            yield event.plain_result(f"✅ 默认社区已设: {label} ({code})")

    async def _run_diagnostics(self, event: AstrMessageEvent):
        import traceback, aiohttp
        yield event.plain_result("🔍 开始诊断…")
        lines = []
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://github.com", timeout=10) as r:
                    lines.append(f"✅ GitHub 连通: HTTP {r.status}")
        except Exception as e:
            lines.append(f"❌ GitHub 不可达: {e}")
        try:
            html = await self._fetcher._fetch_html("daily")
            lines.append(f"✅ Trending 页面: {len(html):,} 字符")
        except Exception as e:
            lines.append(f"❌ Trending 页面: {e}")
        if 'html' in dir():
            try:
                repos = self._fetcher._parse_html(html)
                if repos:
                    lines.append(f"✅ HTML 解析: {len(repos)} 个仓库")
                    r = repos[0]
                    lines.append(f"   示例: {r.full_name} ⭐{r.stars_str} +{r.stars_today_str} today")
                else:
                    lines.append("❌ HTML 解析: 0 个仓库")
            except Exception as e:
                lines.append(f"❌ HTML 解析异常: {e}")
        try:
            repos2 = await self._fetcher.fetch("daily", **self._get_lang_args())
            lines.append(f"✅ 完整 fetch: {len(repos2)} 个仓库")
        except Exception as e:
            lines.append(f"❌ 完整 fetch: {e}")
        if self._translator:
            lines.append("✅ 翻译器: 就绪 (en→zh-CN)")
            try:
                test_result = await self._translator.translate("Hello world test")
                if test_result and test_result != "Hello world test":
                    lines.append(f"   翻译测试: 'Hello world test' → '{test_result}'")
                else:
                    lines.append("   ❌ 翻译测试失败")
            except Exception as e:
                lines.append(f"   ❌ 翻译测试异常: {e}")
        else:
            lines.append("⚠️ 翻译器: 未启用")
        if 'repos2' in dir() and repos2:
            cn = sum(1 for r in repos2 if any('一' <= c <= '鿿' for c in r.description))
            lines.append(f"   翻译覆盖: {cn}/{len(repos2)}")
        lines.append(f"ℹ️ 订阅数: {len(self._config.get('subscriptions', []))}")
        lines.append(f"ℹ️ Token: {'已配置' if self._config.get('github_token', '') else '未配置'}")
        lines.append(f"ℹ️ 代理: {self._config.get('proxy', '') or '未设置'}")
        yield event.plain_result("\n".join(lines))

    async def _show_status(self, event: AstrMessageEvent):
        subs = self._config.get("subscriptions", [])
        enabled_count = sum(1 for s in subs if s.get("enabled", True))
        default_time = self._config.get("push_time", "09:00")
        pl = self._config.get("language", "") or "全语言"
        sl = self._config.get("spoken_language", "") or "不限"
        translate_on = self._config.get("translate_enabled", True)
        has_token = bool(self._config.get("github_token", ""))

        lines = [
            "📊 GitHub Trending 插件状态",
            "─────────────────────────────",
            f"📌 订阅总数: {len(subs)}（已启用 {enabled_count}）",
            f"⏰ 默认推送时间: {default_time}",
            f"📂 默认编程语言: {pl}",
            f"🌍 默认社区: {sl}",
            f"🔑 GitHub Token: {'已设置' if has_token else '未设置'}",
            f"🌐 翻译: {'开启' if translate_on else '关闭'}",
            f"🔀 代理: {self._config.get('proxy', '') or '未设置'}",
            f"🔖 版本: 1.1.0",
        ]
        yield event.plain_result("\n".join(lines))
