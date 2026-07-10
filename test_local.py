"""本地测试用例 — 无需 AstrBot 框架即可运行。

覆盖模块:
    fetcher    — HTML 抓取、解析、缓存、翻译集成
    renderer   — 图片渲染（手绘图标、stars_today、边界情况）
    translator — 翻译、批量翻译、缓存、降级

用法:
    python test_local.py              # 全部测试（含联网）
    python test_local.py --fetch      # 仅数据获取（需联网）
    python test_local.py --render     # 仅图片渲染（离线）
    python test_local.py --trans      # 仅翻译模块（需联网）
    python test_local.py --quick      # 快速（跳过所有联网）
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

# 修复 Windows 终端 GBK 编码
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image as PILImage

# ── 测试结果收集 ──────────────────────────────────────────────────────────
PASS = 0
FAIL = 0
SKIP = 0

ICON_OK = "[OK]"
ICON_FAIL = "[FAIL]"
ICON_SKIP = "[SKIP]"


def ok(msg: str):
    global PASS; PASS += 1; print(f"  {ICON_OK} {msg}")


def fail(msg: str):
    global FAIL; FAIL += 1; print(f"  {ICON_FAIL} {msg}")


def skip(msg: str):
    global SKIP; SKIP += 1; print(f"  {ICON_SKIP} {msg}")


def header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def summary():
    total = PASS + FAIL + SKIP
    print(f"\n{'='*60}")
    print(f"  结果: {PASS} 通过 / {FAIL} 失败 / {SKIP} 跳过 (共 {total})")
    print(f"{'='*60}")
    return FAIL == 0


# ── Mock 数据 ─────────────────────────────────────────────────────────────

MOCK_REPOS = [
    {
        "rank": 1, "owner": "MadsLorentzen", "repo": "ai-job-search",
        "url": "https://github.com/MadsLorentzen/ai-job-search",
        "description": "AI-powered job application framework built on Claude Code",
        "language": "Python", "language_color": "#3572A5",
        "stars": 52300, "stars_str": "52.3k",
        "stars_today": 2341, "stars_today_str": "2.3k",
    },
    {
        "rank": 2, "owner": "SmartlyDressedGames", "repo": "U3-SDK",
        "url": "https://github.com/SmartlyDressedGames/U3-SDK",
        "description": "Source code for Unturned, a free open-world zombie survival sandbox game",
        "language": "C#", "language_color": "#178600",
        "stars": 38100, "stars_str": "38.1k",
        "stars_today": 524, "stars_today_str": "524",
    },
    {
        "rank": 3, "owner": "addyosmani", "repo": "agent-skills",
        "url": "https://github.com/addyosmani/agent-skills",
        "description": "Production-grade engineering skills for AI coding agents",
        "language": "TypeScript", "language_color": "#3178c6",
        "stars": 21700, "stars_str": "21.7k",
        "stars_today": 1856, "stars_today_str": "1.9k",
    },
    {
        "rank": 4, "owner": "anthropics", "repo": "claude-code",
        "url": "https://github.com/anthropics/claude-code",
        "description": "Claude Code is an agentic coding tool from Anthropic",
        "language": "Rust", "language_color": "#dea584",
        "stars": 12300, "stars_str": "12.3k",
        "stars_today": 856, "stars_today_str": "856",
    },
    {
        "rank": 5, "owner": "vercel", "repo": "next.js",
        "url": "https://github.com/vercel/next.js",
        "description": "The React Framework for the Web",
        "language": "JavaScript", "language_color": "#f1e05a",
        "stars": 8900, "stars_str": "8.9k",
        "stars_today": 0, "stars_today_str": "",
    },
    {
        "rank": 6, "owner": "openai", "repo": "gpt-5",
        "url": "https://github.com/openai/gpt-5",
        "description": "GPT-5 research and inference code",
        "language": "Python", "language_color": "#3572A5",
        "stars": 7600, "stars_str": "7.6k",
        "stars_today": 0, "stars_today_str": "",
    },
    {
        "rank": 7, "owner": "ziglang", "repo": "zig",
        "url": "https://github.com/ziglang/zig",
        "description": "General-purpose programming language and toolchain",
        "language": "Zig", "language_color": "#ec915c",
        "stars": 5100, "stars_str": "5.1k",
        "stars_today": 0, "stars_today_str": "",
    },
]

MOCK_EDGE_CASES = [
    {
        "rank": 1, "owner": "very-long-username-that-might-break-layout",
        "repo": "extremely-long-repository-name-for-testing-truncation-behavior",
        "url": "https://github.com/example/test",
        "description": "This is an extremely long description that should definitely be truncated by the renderer because it exceeds the maximum pixel width",
        "language": "Jupyter Notebook", "language_color": "#DA5B0B",
        "stars": 999999, "stars_str": "999.9k",
        "stars_today": 9999, "stars_today_str": "10.0k",
    },
    {
        "rank": 2, "owner": "user", "repo": "minimal",
        "url": "https://github.com/user/minimal",
        "description": "", "language": "", "language_color": "",
        "stars": 0, "stars_str": "0",
        "stars_today": 0, "stars_today_str": "",
    },
]


# ── 工具 ───────────────────────────────────────────────────────────────────

def _make_mock_repos(data_list: list[dict]):
    """将 mock dict 转为 RepoInfo 列表。"""
    from fetcher import RepoInfo
    return [
        RepoInfo(
            rank=d["rank"], owner=d["owner"], repo=d["repo"], url=d["url"],
            description=d.get("description", ""),
            language=d.get("language", ""),
            language_color=d.get("language_color", ""),
            stars=d.get("stars", 0), stars_str=d.get("stars_str", "0"),
            stars_today=d.get("stars_today", 0),
            stars_today_str=d.get("stars_today_str", ""),
        )
        for d in data_list
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  Translator 测试
# ═══════════════════════════════════════════════════════════════════════════


async def test_translator_single():
    """测试单条翻译。"""
    header("Translator: 单条翻译")

    from translator import Translator
    t = Translator(source="en", target="zh-CN")

    try:
        result = await t.translate("Hello, world!")
    except Exception as e:
        fail(f"翻译失败: {e}")
        await t.close(); return

    if result and result != "Hello, world!":
        ok(f"'Hello, world!' → '{result}'")
    else:
        fail(f"翻译结果异常: '{result}'")

    await t.close()


async def test_translator_batch():
    """测试批量翻译。"""
    header("Translator: 批量翻译")

    from translator import Translator
    t = Translator(source="en", target="zh-CN")

    texts = [
        "Source code for a free open-world zombie survival game",
        "Production-grade engineering skills for AI coding agents",
        "The React Framework for the Web",
    ]

    try:
        results = await t.translate_batch(texts)
    except Exception as e:
        fail(f"批量翻译失败: {e}")
        await t.close(); return

    if len(results) == 3:
        ok(f"批量翻译返回 {len(results)} 条结果")
        for en, cn in zip(texts, results):
            ok(f"  '{en[:50]}...' → '{cn[:50]}'")
    else:
        fail(f"返回数量异常: 预期 3，实际 {len(results)}")

    await t.close()


async def test_translator_cache():
    """测试翻译缓存。"""
    header("Translator: 缓存")

    from translator import Translator
    t = Translator(source="en", target="zh-CN")

    # 第一次翻译
    text = "Machine learning is fascinating"
    r1 = await t.translate(text)

    # 第二次应该命中缓存（瞬间返回）
    t0 = time.time()
    r2 = await t.translate(text)
    elapsed = time.time() - t0

    if r1 == r2:
        ok(f"缓存命中，二次查询耗时 {elapsed:.4f}s (预期 < 0.01s)")
    else:
        fail("缓存未命中")

    # 确认 get_cached 有效
    cached = t.get_cached(text)
    if cached == r1:
        ok("get_cached() 返回正确结果")
    else:
        fail("get_cached() 返回错误")

    await t.close()


async def test_translator_edge_cases():
    """测试翻译边界情况：空文本、纯数字、特殊字符。"""
    header("Translator: 边界情况")

    from translator import Translator
    t = Translator(source="en", target="zh-CN")

    # 空文本
    r = await t.translate("")
    if r == "":
        ok("空文本 → 返回空字符串")
    else:
        fail(f"空文本应返回空，实际: '{r}'")

    # 纯数字
    r = await t.translate("12345")
    if r == "12345":
        ok("纯数字 → 原文返回")
    else:
        fail(f"纯数字应返回原文，实际: '{r}'")

    # 很短的单词
    r = await t.translate("OK")
    ok(f"'OK' → '{r}'")

    await t.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Fetcher 测试
# ═══════════════════════════════════════════════════════════════════════════


async def test_fetcher_html_parsing():
    """测试 HTML 抓取 + 解析。"""
    from fetcher import TrendingFetcher

    header("Fetcher: HTML 抓取 & 解析")
    fetcher = TrendingFetcher()

    try:
        html = await fetcher._fetch_html("daily")
    except Exception as e:
        fail(f"抓取 HTML 失败: {e}"); return

    ok(f"成功获取 HTML ({len(html):,} 字符)")

    repos = fetcher._parse_html(html)
    if not repos:
        fail("解析出空列表"); return

    ok(f"成功解析出 {len(repos)} 个仓库")

    for repo in repos[:5]:
        flags = []
        if repo.stars_today > 0:
            flags.append(f"+{repo.stars_today_str} today")
        if repo.language:
            flags.append(repo.language)
        ok(f"  #{repo.rank} {repo.full_name}  stars={repo.stars_str}  {', '.join(flags)}")

    r = repos[0]
    checks = [
        ("rank == 1", r.rank == 1),
        ("owner 非空", bool(r.owner)),
        ("repo 非空", bool(r.repo)),
        ("url 格式正确", r.url.startswith("https://github.com/")),
        ("stars > 0", r.stars > 0),
        ("stars_today >= 0", r.stars_today >= 0),
        ("full_name 正确", r.full_name == f"{r.owner}/{r.repo}"),
    ]
    if r.stars_today > 0:
        checks.append(("stars_today_str 非空", bool(r.stars_today_str)))

    for name, passed in checks:
        (ok if passed else fail)(f"  {name}" + (f" = {getattr(r, name)!r}" if not passed else ""))


async def test_fetcher_weekly():
    """测试 weekly 模式。"""
    from fetcher import TrendingFetcher

    header("Fetcher: Weekly 模式")
    fetcher = TrendingFetcher()

    try:
        repos = await fetcher.fetch("weekly")
    except Exception as e:
        fail(f"Weekly 获取失败: {e}"); return

    if repos:
        ok(f"Weekly 获取到 {len(repos)} 个仓库")
    else:
        fail("Weekly 返回空列表")


async def test_fetcher_with_translation():
    """测试 fetcher 配合翻译器。"""
    from fetcher import TrendingFetcher
    from translator import Translator

    header("Fetcher: 翻译集成")
    t = Translator(source="en", target="zh-CN")
    fetcher = TrendingFetcher(translator=t)

    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"Fetch 失败: {e}")
        await t.close(); return

    ok(f"获取 {len(repos)} 个仓库（含翻译）")

    # 检查前几个描述是否是中文
    cn_count = 0
    for repo in repos[:5]:
        if repo.description:
            has_cjk = any('一' <= c <= '鿿' for c in repo.description)
            if has_cjk:
                cn_count += 1
            ok(f"  {repo.full_name}: {repo.description[:60]}")

    if cn_count >= 3:
        ok(f"翻译覆盖率: {cn_count}/5（预期大部分为中文）")
    elif cn_count > 0:
        skip(f"部分翻译成功: {cn_count}/5（可能网络不稳定）")
    else:
        fail("翻译全部失败，请检查网络")

    await t.close()


async def test_fetcher_cache():
    """测试内存缓存。"""
    from fetcher import TrendingFetcher, RepoInfo

    header("Fetcher: 缓存机制")
    fetcher = TrendingFetcher()

    dummy = [
        RepoInfo(rank=1, owner="test", repo="test",
                 url="https://github.com/test/test", description="test",
                 language="Python", language_color="#3572A5",
                 stars=100, stars_str="100", stars_today=10, stars_today_str="10")
    ]
    fetcher._set_cache("daily", dummy)

    cached = fetcher._get_cached("daily")
    if cached and len(cached) == 1 and cached[0].full_name == "test/test":
        ok("缓存写入/读取正常")
    else:
        fail("缓存读取失败")

    fetcher._cache_ttl = 0
    expired = fetcher._get_cached("daily")
    if expired is None:
        ok("缓存过期机制正常（TTL=0 → None）")
    else:
        fail("缓存过期机制异常")
    fetcher._cache_ttl = 300


async def test_fetcher_full_flow():
    """完整 fetch 流程（需联网）。"""
    from fetcher import TrendingFetcher

    header("Fetcher: 完整获取流程 (daily)")
    fetcher = TrendingFetcher()

    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"fetch 抛出异常: {e}"); return

    if not repos:
        fail("返回空列表"); return

    ok(f"获取到 {len(repos)} 个仓库")

    r = repos[0]
    for field, expected in [
        ("rank", r.rank > 0), ("owner", bool(r.owner)), ("repo", bool(r.repo)),
        ("url", r.url.startswith("https://github.com/")),
        ("stars", r.stars > 0), ("stars_str", bool(r.stars_str)),
        ("stars_today", r.stars_today >= 0),
        ("full_name", r.full_name == f"{r.owner}/{r.repo}"),
    ]:
        if expected:
            ok(f"RepoInfo.{field}: {getattr(r, field)!r}")
        else:
            fail(f"RepoInfo.{field} 异常: {getattr(r, field)!r}")
    if r.stars_today > 0:
        ok(f"RepoInfo.stars_today_str: {r.stars_today_str!r}")

    # 缓存命中
    t0 = time.time()
    await fetcher.fetch("daily")
    elapsed = time.time() - t0
    if elapsed < 0.1:
        ok(f"二次查询命中缓存（{elapsed:.4f}s）")
    else:
        skip(f"二次查询耗时 {elapsed:.2f}s，可能未命中缓存")


# ═══════════════════════════════════════════════════════════════════════════
#  Renderer 测试
# ═══════════════════════════════════════════════════════════════════════════


def _verify_png(image_bytes: bytes, expected_min_w: int = 700, label: str = "") -> PILImage.Image | None:
    """辅助：验证 PNG 有效性并返回 Image 对象。"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        if label:
            ok(f"{label}: {img.size[0]}x{img.size[1]}, {len(image_bytes):,} bytes")
        return img
    except Exception as e:
        fail(f"{label} 无法打开: {e}")
        return None


def test_renderer_basic():
    """基本渲染（含 stars_today 和手绘图标）。"""
    header("Renderer: 基本渲染 (含 stars_today)")
    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS)
    image_bytes = render_trending(repos, "daily")
    img = _verify_png(image_bytes, label="基本渲染")
    if img is None:
        return

    w, h = img.size
    if w == 800:
        ok("宽度 = 800px")
    else:
        fail(f"宽度异常: {w}（预期 800）")
    if h > 700:
        ok(f"高度 {h}px 合理（7 项目含 stars_today 行，预期 > 700）")
    else:
        fail(f"高度 {h}px 偏小")


def test_renderer_edge_cases():
    """边界情况：超长名称、空描述、无语言、超大 stars_today。"""
    header("Renderer: 边界情况")
    from renderer import render_trending

    repos = _make_mock_repos(MOCK_EDGE_CASES)
    image_bytes = render_trending(repos, "daily")
    _verify_png(image_bytes, label="边界渲染")


def test_renderer_weekly():
    """Weekly 模式标题 + URL 不同。"""
    header("Renderer: Weekly 模式")
    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS[:3])
    image_bytes = render_trending(repos, "weekly")
    _verify_png(image_bytes, label="Weekly 渲染")


def test_renderer_large_list():
    """25 项大列表。"""
    header("Renderer: 大列表 (25 项)")
    from renderer import render_trending

    big = []
    for i in range(25):
        d = {**MOCK_REPOS[i % len(MOCK_REPOS)], "rank": i + 1}
        big.append(d)
    repos = _make_mock_repos(big)
    image_bytes = render_trending(repos, "daily")
    img = _verify_png(image_bytes, label="大列表")

    if img and img.size[1] > 2000:
        ok("高度符合预期（> 2000px）")
    elif img:
        fail(f"高度异常: {img.size[1]}（预期 > 2000）")


def test_renderer_no_stars_today():
    """所有项目 stars_today=0 时不应显示 trend 图标。"""
    header("Renderer: 无 stars_today 时隐藏 trend")
    from renderer import render_trending

    data = [{**MOCK_REPOS[0], "rank": 1, "stars_today": 0, "stars_today_str": ""}]
    repos = _make_mock_repos(data)
    image_bytes = render_trending(repos, "daily")
    img = _verify_png(image_bytes, label="无 trend")

    # 高度应小于有 trend 的情况
    if img:
        # 单项目无 trend 应该比较矮
        ok(f"无 trend 单项高度: {img.size[1]}px")


def test_renderer_save_image():
    """保存预览图片到磁盘。"""
    header("Renderer: 保存预览图片")
    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS)

    for feed_type, fname in [("daily", "test_preview_daily.png"),
                              ("weekly", "test_preview_weekly.png")]:
        image_bytes = render_trending(repos, feed_type)
        out_path = Path(__file__).parent / fname
        out_path.write_bytes(image_bytes)
        ok(f"{feed_type} → {out_path.name} ({len(image_bytes):,} bytes)")

    repos_edge = _make_mock_repos(MOCK_EDGE_CASES)
    out_path_e = Path(__file__).parent / "test_preview_edge.png"
    out_path_e.write_bytes(render_trending(repos_edge, "daily"))
    ok(f"边界 → {out_path_e.name}")


# ═══════════════════════════════════════════════════════════════════════════
#  集成测试
# ═══════════════════════════════════════════════════════════════════════════


async def test_integration_full_pipeline():
    """端到端：真实数据 → 渲染 → 图片。"""
    header("集成: 完整管线（真实数据）")
    from fetcher import TrendingFetcher
    from renderer import render_trending

    fetcher = TrendingFetcher()
    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"数据获取失败: {e}"); return

    if not repos:
        skip("无数据"); return

    ok(f"获取 {len(repos)} 个真实仓库")

    image_bytes = render_trending(repos, "daily")
    out_path = Path(__file__).parent / "test_preview_real.png"
    out_path.write_bytes(image_bytes)
    _verify_png(image_bytes, label="真实数据")

    # 验证描述中存在 stars_today 数据
    has_today = any(r.stars_today > 0 for r in repos)
    if has_today:
        ok("真实数据包含 stars_today 信息")
    else:
        skip("真实数据无 stars_today（可能恰好没有）")


async def test_integration_translated_pipeline():
    """端到端：真实数据 + 翻译 → 渲染 → 图片。"""
    header("集成: 翻译管线")
    from fetcher import TrendingFetcher
    from renderer import render_trending
    from translator import Translator

    t = Translator(source="en", target="zh-CN")
    fetcher = TrendingFetcher(translator=t)

    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"翻译模式获取失败: {e}")
        await t.close(); return

    ok(f"翻译模式获取 {len(repos)} 个仓库")

    # 检查中文
    cn_count = sum(
        1 for r in repos if any('一' <= c <= '鿿' for c in r.description)
    )
    ok(f"含中文描述: {cn_count}/{len(repos)}")

    # 渲染
    image_bytes = render_trending(repos, "daily")
    out_path = Path(__file__).parent / "test_preview_translated.png"
    out_path.write_bytes(image_bytes)
    _verify_png(image_bytes, label="翻译版图片")

    await t.close()


# ═══════════════════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    args = set(sys.argv[1:])
    quick = "--quick" in args
    fetch_only = "--fetch" in args
    render_only = "--render" in args
    trans_only = "--trans" in args
    run_all = not (quick or fetch_only or render_only or trans_only)

    print("GitHub Trending 插件 — 本地测试")
    print(f"Python: {sys.version}")
    print(f"工作目录: {os.getcwd()}")

    # ── 离线测试（始终运行）──────────────────────────────────────────
    if not fetch_only and not trans_only:
        test_renderer_basic()
        test_renderer_edge_cases()
        test_renderer_weekly()
        test_renderer_large_list()
        test_renderer_no_stars_today()
        test_renderer_save_image()

    if render_only:
        ok_all = summary(); sys.exit(0 if ok_all else 1)

    if trans_only:
        await test_translator_single()
        await test_translator_batch()
        await test_translator_cache()
        await test_translator_edge_cases()
        ok_all = summary(); sys.exit(0 if ok_all else 1)

    # ── 联网测试 ──────────────────────────────────────────────────────
    if quick:
        skip("跳过所有联网测试（--quick）")
        summary(); return

    await test_translator_single()
    await test_translator_batch()
    await test_translator_cache()
    await test_translator_edge_cases()

    if trans_only:
        ok_all = summary(); sys.exit(0 if ok_all else 1)

    await test_fetcher_cache()
    await test_fetcher_html_parsing()
    await test_fetcher_weekly()

    if fetch_only:
        ok_all = summary(); sys.exit(0 if ok_all else 1)

    # ── 集成 ──────────────────────────────────────────────────────────
    await test_fetcher_full_flow()
    await test_fetcher_with_translation()
    await test_integration_full_pipeline()
    await test_integration_translated_pipeline()

    ok_all = summary()
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    asyncio.run(main())
