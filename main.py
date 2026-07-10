"""GitHub Trending AstrBot 插件。

功能：
- /trending — 手动获取每日 GitHub Trending 榜单
- /trending weekly — 获取本周榜单
- /trending addhere — 将当前会话加入每日推送
- /trending delhere — 将当前会话移出每日推送
- /trending list — 查看所有推送目标
- /trending time HH:MM — 设置每日推送时间
- /trending token <ghp_xxx> — 设置 GitHub Token
- /trending status — 查看当前配置

定时任务：每天在设定的时间自动获取榜单并推送到所有已配置目标。
"""
from __future__ import annotations

import asyncio
import base64
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
    "targets": [],
    "push_time": "09:00",
    "github_token": "",
    "translate_enabled": True,
    "proxy": "",  # 代理地址，如 http://127.0.0.1:7890
}

PLUGIN_NAME = "astrbot_plugin_github_trending"


@register(PLUGIN_NAME, "MillionDream", "每日 GitHub Trending 榜单推送插件", "1.0.0")
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

    def _sync_proxy(self):
        """将代理配置同步到 fetcher 和 translator。"""
        proxy = self._config.get("proxy", "")
        self._fetcher._proxy = proxy
        if hasattr(self._fetcher, "clear_cache"):
            self._fetcher.clear_cache()
        if self._translator:
            self._translator._proxy = proxy

    def _init_translator(self):
        """根据配置初始化或销毁翻译器。"""
        proxy = self._config.get("proxy", "")
        if self._config.get("translate_enabled", True):
            if self._translator is None:
                self._translator = Translator(source="en", target="zh-CN", proxy=proxy)
        else:
            if self._translator:
                self._translator = None
        # 同步到 fetcher
        if hasattr(self, "_fetcher"):
            self._fetcher._translator = self._translator
            self._fetcher.clear_cache()

    # ── 生命周期 ───────────────────────────────────────────────────────

    async def initialize(self):
        """插件初始化：加载持久化配置，启动定时任务。"""
        await self._load_config()
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            f"[GitHubTrending] 插件已启动，推送时间: {self._config['push_time']}，"
            f"目标数量: {len(self._config['targets'])}"
        )

    async def terminate(self):
        """插件销毁：取消定时任务。"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("[GitHubTrending] 插件已停止")

    # ── 配置持久化 ─────────────────────────────────────────────────────

    async def _load_config(self):
        """从 KV 存储加载配置。"""
        saved = await self.get_kv_data("config", None)
        if saved:
            self._config.update(saved)
        # 同步翻译器
        self._init_translator()
        # 同步代理到 fetcher 和 translator
        self._sync_proxy()
        # 同步 GitHub token 到 fetcher
        token = self._config.get("github_token", "")
        if token:
            self._fetcher._token = token

    async def _save_config(self):
        """保存配置到 KV 存储。"""
        await self.put_kv_data("config", self._config)

    # ── 定时任务 ───────────────────────────────────────────────────────

    async def _scheduler_loop(self):
        """后台定时推送循环。"""
        while self._running:
            try:
                # 计算到下一次推送的等待秒数
                sleep_seconds = self._calc_sleep_seconds()
                logger.info(
                    f"[GitHubTrending] 下次推送时间: "
                    f"{datetime.now() + timedelta(seconds=sleep_seconds):%Y-%m-%d %H:%M:%S}"
                )
                await asyncio.sleep(sleep_seconds)

                if not self._running:
                    break

                # 执行推送
                await self._do_daily_push()

                # 避免重复触发：等 60 秒
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[GitHubTrending] 定时任务异常，60 秒后重试")
                await asyncio.sleep(60)

    def _calc_sleep_seconds(self) -> float:
        """计算到下一次推送时间的秒数。"""
        now = datetime.now()
        time_str = self._config.get("push_time", "09:00")
        try:
            hour, minute = map(int, time_str.split(":"))
        except (ValueError, TypeError):
            hour, minute = 9, 0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        return (target - now).total_seconds()

    async def _do_daily_push(self):
        """执行每日推送：拉取数据 → 渲染图片 → 发送到所有目标。"""
        targets = self._config.get("targets", [])
        if not targets:
            logger.warning("[GitHubTrending] 没有配置推送目标，跳过推送")
            return

        logger.info(f"[GitHubTrending] 开始每日推送，目标数: {len(targets)}")

        try:
            repos = await self._fetcher.fetch("daily")
            image_bytes = render_trending(repos, "daily")
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            links_text = self._build_links_text(repos, "daily")
            await self._broadcast(b64, "daily", links_text)
            logger.info(f"[GitHubTrending] 每日推送完成，{len(repos)} 个项目")
        except Exception:
            logger.exception("[GitHubTrending] 每日推送失败")

    async def _broadcast(self, b64_image: str, feed_type: str, links_text: str = ""):
        """将图片广播到所有配置的目标。"""
        from astrbot.core.message.message_event_result import MessageChain

        title = "GitHub Trending Daily" if feed_type == "daily" else "GitHub Trending Weekly"

        chain = MessageChain()
        chain.chain = [
            Plain(f"🔥 {title}\n"),
            Image.fromBase64(b64_image),
        ]
        if links_text:
            chain.chain.append(Plain(f"\n{links_text}"))

        for target in self._config.get("targets", []):
            umo = target.get("umo", "")
            if not umo:
                continue
            try:
                await self.context.send_message(umo, chain)
                await asyncio.sleep(0.5)  # 避免发送过快
            except Exception:
                logger.exception(f"[GitHubTrending] 发送到 {umo} 失败")

    # ── 手动触发（渲染+发送的公共逻辑） ─────────────────────────────────

    @staticmethod
    def _build_links_text(repos: list, feed_type: str) -> str:
        """生成榜单链接 + Top 5 直达链接文本。"""
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
        """拉取数据、渲染图片、回复给当前会话。"""
        yield event.plain_result(f"🔍 正在获取 GitHub Trending {feed_type} 榜单...")

        try:
            repos = await self._fetcher.fetch(feed_type)
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

        # 回复图片（base64） + 链接
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        chain = [Image.fromBase64(b64)]
        yield event.chain_result(chain)
        yield event.plain_result(self._build_links_text(repos, feed_type))

    # ── 指令处理 ───────────────────────────────────────────────────────

    @filter.command("trending")
    async def trending(self, event: AstrMessageEvent):
        """/trending — GitHub Trending 榜单主指令。

        子命令:
            (无)         — 获取 daily 榜单
            weekly       — 获取 weekly 榜单
            addhere      — 将当前会话加入每日推送
            delhere      — 将当前会话移出每日推送
            list         — 查看所有推送目标
            time HH:MM   — 设置每日推送时间
            token <ghp>  — 设置 GitHub API Token
            status       — 查看当前配置
        """
        # 解析子命令
        msg = event.message_str.strip()
        parts = msg.split(maxsplit=1)
        subcmd_and_args = parts[1] if len(parts) > 1 else ""
        sub_parts = subcmd_and_args.split(maxsplit=1)
        subcmd = sub_parts[0].lower() if sub_parts else ""
        arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""

        # ── 分发 ───────────────────────────────────────────────────
        if subcmd in ("", "daily"):
            async for result in self._fetch_and_send(event, "daily"):
                yield result

        elif subcmd == "weekly":
            async for result in self._fetch_and_send(event, "weekly"):
                yield result

        elif subcmd == "addhere":
            async for result in self._add_target(event):
                yield result

        elif subcmd == "delhere":
            async for result in self._del_target(event):
                yield result

        elif subcmd == "list":
            async for result in self._list_targets(event):
                yield result

        elif subcmd == "time":
            async for result in self._set_time(event, arg):
                yield result

        elif subcmd == "token":
            async for result in self._set_token(event, arg):
                yield result

        elif subcmd == "lang":
            async for result in self._toggle_lang(event, arg):
                yield result

        elif subcmd == "proxy":
            async for result in self._set_proxy(event, arg):
                yield result

        elif subcmd == "debug":
            async for result in self._run_diagnostics(event):
                yield result

        elif subcmd == "status":
            async for result in self._show_status(event):
                yield result

        else:
            yield event.plain_result(
                f"⚠️ 未知子命令: {subcmd}\n"
                "可用子命令: weekly, addhere, delhere, list, time, token, lang, proxy, debug, status"
            )

    # ── 子命令实现 ─────────────────────────────────────────────────────

    async def _add_target(self, event: AstrMessageEvent):
        """将当前会话加入推送列表。"""
        umo = event.unified_msg_origin
        if not umo:
            yield event.plain_result("❌ 无法获取当前会话标识。")
            return

        # 判断会话类型
        target_type = "group" if "group" in umo.lower() else "user"

        # 检查是否已存在
        for t in self._config["targets"]:
            if t.get("umo") == umo:
                yield event.plain_result(f"ℹ️ 当前会话已在推送列表中。")
                return

        self._config["targets"].append({"type": target_type, "umo": umo})
        await self._save_config()
        yield event.plain_result(
            f"✅ 已将当前{'群聊' if target_type == 'group' else '私聊'}加入每日推送列表！\n"
            f"推送时间: {self._config['push_time']}\n"
            f"当前目标数: {len(self._config['targets'])}"
        )

    async def _del_target(self, event: AstrMessageEvent):
        """将当前会话移出推送列表。"""
        umo = event.unified_msg_origin
        if not umo:
            yield event.plain_result("❌ 无法获取当前会话标识。")
            return

        before = len(self._config["targets"])
        self._config["targets"] = [
            t for t in self._config["targets"] if t.get("umo") != umo
        ]

        if len(self._config["targets"]) == before:
            yield event.plain_result("ℹ️ 当前会话不在推送列表中。")
            return

        await self._save_config()
        yield event.plain_result(
            f"✅ 已将当前会话移出每日推送列表。\n"
            f"当前目标数: {len(self._config['targets'])}"
        )

    async def _list_targets(self, event: AstrMessageEvent):
        """列出所有推送目标。"""
        targets = self._config.get("targets", [])
        if not targets:
            yield event.plain_result("📭 当前没有配置推送目标。\n使用 /trending addhere 添加当前会话。")
            return

        lines = [f"📋 推送目标列表 (共 {len(targets)} 个):\n"]
        for i, t in enumerate(targets, 1):
            t_type = "群聊" if t.get("type") == "group" else "私聊"
            lines.append(f"  {i}. [{t_type}] {t.get('umo', 'unknown')}")
        lines.append(f"\n⏰ 推送时间: {self._config.get('push_time', '09:00')}")

        yield event.plain_result("\n".join(lines))

    async def _set_time(self, event: AstrMessageEvent, arg: str):
        """设置每日推送时间。"""
        if not arg:
            yield event.plain_result(
                "⚠️ 请指定时间，格式: /trending time HH:MM\n例如: /trending time 09:00"
            )
            return

        # 校验格式
        try:
            hour, minute = map(int, arg.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except (ValueError, TypeError):
            yield event.plain_result("⚠️ 时间格式无效，请使用 HH:MM 格式，例如: 09:00")
            return

        self._config["push_time"] = arg
        await self._save_config()
        yield event.plain_result(
            f"✅ 每日推送时间已设置为 {arg}\n"
            f"（注：修改将在下一次推送后生效，或重启插件立即生效）"
        )

    async def _set_token(self, event: AstrMessageEvent, arg: str):
        """设置 GitHub API Token。"""
        if not arg:
            yield event.plain_result(
                "⚠️ 请提供 GitHub Token。\n"
                "获取方式: GitHub Settings → Developer settings → Personal access tokens\n"
                "用法: /trending token ghp_xxxxxxxxxxxx"
            )
            return

        token = arg.strip()
        self._config["github_token"] = token
        self._fetcher._token = token
        self._fetcher.clear_cache()
        await self._save_config()
        yield event.plain_result(
            f"✅ GitHub Token 已设置。\n"
            f"Token 前缀: {token[:8]}...\n"
            f"（已清除缓存，下次请求将使用新 Token）"
        )

    async def _toggle_lang(self, event: AstrMessageEvent, arg: str):
        """开关描述翻译。"""
        enabled = self._config.get("translate_enabled", True)

        if arg and arg.lower() == "off":
            self._config["translate_enabled"] = False
            self._init_translator()
            await self._save_config()
            yield event.plain_result("✅ 描述翻译已关闭，将显示英文原文。")
        elif arg and arg.lower() == "on":
            self._config["translate_enabled"] = True
            self._init_translator()
            await self._save_config()
            yield event.plain_result("✅ 描述翻译已开启，将显示中文翻译。")
        else:
            state = "开启 ✅" if enabled else "关闭 ❌"
            yield event.plain_result(
                f"翻译状态: {state}\n"
                "用法:\n"
                "  /trending lang on  — 开启中文翻译\n"
                "  /trending lang off — 关闭（显示英文原文）"
            )

    async def _set_proxy(self, event: AstrMessageEvent, arg: str):
        """设置代理。"""
        if not arg or arg.lower() == "none":
            self._config["proxy"] = ""
            self._sync_proxy()
            await self._save_config()
            yield event.plain_result("✅ 代理已清除，将使用直连。")
        else:
            proxy = arg.strip()
            # 基本校验
            if not proxy.startswith("http://") and not proxy.startswith("https://") and not proxy.startswith("socks5://"):
                yield event.plain_result("⚠️ 代理格式无效，请使用 http://host:port 或 socks5://host:port")
                return
            self._config["proxy"] = proxy
            self._sync_proxy()
            await self._save_config()
            yield event.plain_result(
                f"✅ 代理已设置: {proxy}\n"
                f"（已清除缓存，下次请求将使用代理）"
            )

    async def _run_diagnostics(self, event: AstrMessageEvent):
        """诊断命令：逐项检查网络和解析是否正常。"""
        import traceback
        import aiohttp

        yield event.plain_result("🔍 开始诊断…")
        lines = []

        # 1. 网络连通性
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://github.com", timeout=10) as r:
                    lines.append(f"✅ GitHub 连通: HTTP {r.status}")
        except Exception as e:
            lines.append(f"❌ GitHub 不可达: {e}")

        # 2. Trending 页面
        try:
            html = await self._fetcher._fetch_html("daily")
            lines.append(f"✅ Trending 页面: {len(html):,} 字符")
        except Exception as e:
            lines.append(f"❌ Trending 页面: {e}")

        # 3. HTML 解析
        if 'html' in dir():
            try:
                repos = self._fetcher._parse_html(html)
                if repos:
                    lines.append(f"✅ HTML 解析: {len(repos)} 个仓库")
                    r = repos[0]
                    lines.append(f"   示例: {r.full_name} ⭐{r.stars_str} +{r.stars_today_str} today")
                else:
                    lines.append("❌ HTML 解析: 0 个仓库，可能页面结构已变化")
            except Exception as e:
                lines.append(f"❌ HTML 解析异常: {e}")
                lines.append(f"   {traceback.format_exc()[-300:]}")

        # 4. 完整 fetch（含缓存状态）
        try:
            repos2 = await self._fetcher.fetch("daily")
            lines.append(f"✅ 完整 fetch: {len(repos2)} 个仓库")
        except Exception as e:
            lines.append(f"❌ 完整 fetch: {e}")

        # 5. 翻译状态 + 实际测试
        if self._translator:
            lines.append(f"✅ 翻译器: 就绪 (en→zh-CN)")
            try:
                test_result = await self._translator.translate("Hello world test")
                if test_result and test_result != "Hello world test":
                    lines.append(f"   翻译测试: 'Hello world test' → '{test_result}'")
                else:
                    lines.append(f"   ❌ 翻译测试失败: 返回原文，Google API 可能不可达")
            except Exception as e:
                lines.append(f"   ❌ 翻译测试异常: {e}")
        else:
            lines.append(f"⚠️ 翻译器: 未启用（使用 /trending lang on 开启）")

        # 6. 实际数据中的翻译效果
        if 'repos2' in dir() and repos2:
            cn = sum(1 for r in repos2 if any('一' <= c <= '鿿' for c in r.description))
            lines.append(f"   实际翻译覆盖: {cn}/{len(repos2)} 条描述含中文")
            if cn == 0:
                lines.append(f"   ⚠️ 翻译未生效，请检查服务器能否访问 translate.googleapis.com")

        # 6. 配置
        token = self._config.get("github_token", "")
        proxy = self._config.get("proxy", "")
        lines.append(f"ℹ️ Token: {'已配置' if token else '未配置'}")
        lines.append(f"ℹ️ 代理: {proxy if proxy else '未设置（直连）'}")
        lines.append(f"ℹ️ 推送目标: {len(self._config.get('targets', []))} 个")

        yield event.plain_result("\n".join(lines))

    async def _show_status(self, event: AstrMessageEvent):
        """显示当前配置状态。"""
        targets = self._config.get("targets", [])
        push_time = self._config.get("push_time", "09:00")
        has_token = bool(self._config.get("github_token", ""))
        translate_on = self._config.get("translate_enabled", True)

        # 计算下次推送时间
        sleep_sec = self._calc_sleep_seconds()
        next_push = datetime.now() + timedelta(seconds=sleep_sec)

        lines = [
            "📊 GitHub Trending 插件状态",
            "─────────────────────────────",
            f"⏰ 推送时间: {push_time}",
            f"🕐 下次推送: {next_push:%Y-%m-%d %H:%M:%S}",
            f"📌 推送目标: {len(targets)} 个",
            f"🔑 GitHub Token: {'已设置' if has_token else '未设置'}",
            f"🌐 描述翻译: {'开启 (英文→中文)' if translate_on else '关闭 (英文原文)'}",
            f"📦 数据来源: GitHub Trending 页面实时抓取",
            f"🔖 插件版本: 1.0.0",
        ]

        yield event.plain_result("\n".join(lines))
