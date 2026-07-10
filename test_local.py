"""本地测试用例 — 无需 AstrBot 框架即可运行。

测试 fetcher（数据获取）和 renderer（图片渲染）模块。

用法:
    python test_local.py              # 运行全部测试
    python test_local.py --fetch      # 仅测试数据获取（需联网）
    python test_local.py --render     # 仅测试图片渲染（离线）
    python test_local.py --quick      # 快速测试（跳过网络请求）
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

# 修复 Windows 终端 GBK 编码下 emoji 输出问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image as PILImage

# ── 测试结果收集 ──────────────────────────────────────────────────────────
PASS = 0
FAIL = 0
SKIP = 0

# ASCII-safe 图标（GBK 终端兼容）
ICON_OK = "[OK]"
ICON_FAIL = "[FAIL]"
ICON_SKIP = "[SKIP]"


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  {ICON_OK} {msg}")


def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  {ICON_FAIL} {msg}")


def skip(msg: str):
    global SKIP
    SKIP += 1
    print(f"  {ICON_SKIP} {msg}")


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
        "rank": 1,
        "owner": "MadsLorentzen",
        "repo": "ai-job-search",
        "url": "https://github.com/MadsLorentzen/ai-job-search",
        "description": "AI-powered job application framework built on Claude Code",
        "language": "Python",
        "language_color": "#3572A5",
        "stars": 52300,
        "stars_str": "52.3k",
    },
    {
        "rank": 2,
        "owner": "SmartlyDressedGames",
        "repo": "U3-SDK",
        "url": "https://github.com/SmartlyDressedGames/U3-SDK",
        "description": "Source code for Unturned, a free open-world zombie survival sandbox game",
        "language": "C#",
        "language_color": "#178600",
        "stars": 38100,
        "stars_str": "38.1k",
    },
    {
        "rank": 3,
        "owner": "addyosmani",
        "repo": "agent-skills",
        "url": "https://github.com/addyosmani/agent-skills",
        "description": "Production-grade engineering skills for AI coding agents with 24 skills",
        "language": "TypeScript",
        "language_color": "#3178c6",
        "stars": 21700,
        "stars_str": "21.7k",
    },
    {
        "rank": 4,
        "owner": "anthropics",
        "repo": "claude-code",
        "url": "https://github.com/anthropics/claude-code",
        "description": "Claude Code is an agentic coding tool from Anthropic",
        "language": "Rust",
        "language_color": "#dea584",
        "stars": 12300,
        "stars_str": "12.3k",
    },
    {
        "rank": 5,
        "owner": "vercel",
        "repo": "next.js",
        "url": "https://github.com/vercel/next.js",
        "description": "The React Framework for the Web",
        "language": "JavaScript",
        "language_color": "#f1e05a",
        "stars": 8900,
        "stars_str": "8.9k",
    },
    {
        "rank": 6,
        "owner": "openai",
        "repo": "gpt-5",
        "url": "https://github.com/openai/gpt-5",
        "description": "GPT-5 research and inference code",
        "language": "Python",
        "language_color": "#3572A5",
        "stars": 7600,
        "stars_str": "7.6k",
    },
    {
        "rank": 7,
        "owner": "ziglang",
        "repo": "zig",
        "url": "https://github.com/ziglang/zig",
        "description": "General-purpose programming language and toolchain",
        "language": "Zig",
        "language_color": "#ec915c",
        "stars": 5100,
        "stars_str": "5.1k",
    },
]

# 超长名称 / 描述的数据，用于测试边界情况
MOCK_EDGE_CASES = [
    {
        "rank": 1,
        "owner": "very-long-username-that-might-break-layout",
        "repo": "extremely-long-repository-name-for-testing-truncation-behavior",
        "url": "https://github.com/example/test",
        "description": "This is an extremely long description that should definitely be truncated by the renderer because it exceeds the maximum pixel width that we have allocated for the description text area in the leaderboard image layout",
        "language": "Jupyter Notebook",
        "language_color": "#DA5B0B",
        "stars": 999999,
        "stars_str": "999.9k",
    },
    {
        "rank": 2,
        "owner": "user",
        "repo": "minimal",
        "url": "https://github.com/user/minimal",
        "description": "",  # 空描述
        "language": "",  # 无语言
        "language_color": "",
        "stars": 0,
        "stars_str": "0",
    },
]


# ── Fetcher 测试 ──────────────────────────────────────────────────────────


async def test_fetcher_html_parsing():
    """测试 HTML 抓取+解析是否正确获取仓库列表。"""
    from fetcher import TrendingFetcher

    header("Fetcher: HTML 抓取 & 解析")

    fetcher = TrendingFetcher()

    try:
        html = await fetcher._fetch_html("daily")
    except Exception as e:
        fail(f"抓取 HTML 失败: {e}")
        return

    ok(f"成功获取 HTML ({len(html):,} 字符)")

    repos = fetcher._parse_html(html)
    if not repos:
        fail("解析出空列表")
        return

    ok(f"成功解析出 {len(repos)} 个仓库")

    # 验证前 5 个条目
    for repo in repos[:5]:
        ok(f"  #{repo.rank} {repo.full_name} ⭐{repo.stars_str}"
           f" {'🔥 +' + repo.stars_today_str if repo.stars_today else ''}"
           f" {'🔴' + repo.language if repo.language else ''}")

    # 验证 RepoInfo 字段完整性
    r = repos[0]
    checks = [
        ("rank == 1", r.rank == 1),
        ("owner 非空", bool(r.owner)),
        ("repo 非空", bool(r.repo)),
        ("url 格式正确", r.url.startswith("https://github.com/")),
        ("stars > 0", r.stars > 0),
        ("full_name 正确", r.full_name == f"{r.owner}/{r.repo}"),
    ]
    for name, passed in checks:
        if passed:
            ok(f"  {name}")
        else:
            fail(f"  {name}: {getattr(r, name, 'N/A')!r}")


async def test_fetcher_cache():
    """测试内存缓存机制。"""
    from fetcher import TrendingFetcher

    header("Fetcher: 缓存机制")

    fetcher = TrendingFetcher()

    # 写缓存
    from fetcher import RepoInfo

    dummy = [
        RepoInfo(
            rank=1,
            owner="test",
            repo="test",
            url="https://github.com/test/test",
            description="test",
            language="Python",
            language_color="#3572A5",
            stars=100,
            stars_str="100",
        )
    ]
    fetcher._set_cache("daily", dummy)

    # 读缓存
    cached = fetcher._get_cached("daily")
    if cached and len(cached) == 1 and cached[0].full_name == "test/test":
        ok("缓存写入/读取正常")
    else:
        fail("缓存读取失败")

    # 测试过期
    fetcher._cache_ttl = 0  # 立即过期
    expired = fetcher._get_cached("daily")
    if expired is None:
        ok("缓存过期机制正常（TTL=0 时返回 None）")
    else:
        fail("缓存过期机制异常：TTL=0 但仍返回数据")

    fetcher._cache_ttl = 300  # 恢复默认


async def test_fetcher_full_flow():
    """测试完整 fetch 流程（需联网）。"""
    from fetcher import TrendingFetcher

    header("Fetcher: 完整获取流程 (daily)")

    fetcher = TrendingFetcher()

    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"fetch 抛出异常: {e}")
        return

    if not repos:
        fail("返回空列表")
        return

    ok(f"获取到 {len(repos)} 个仓库")

    # 验证 RepoInfo 结构
    r = repos[0]
    checks = [
        ("rank", r.rank > 0),
        ("owner", bool(r.owner)),
        ("repo", bool(r.repo)),
        ("url", r.url.startswith("https://github.com/")),
        ("stars", r.stars > 0),
        ("stars_str", bool(r.stars_str)),
        ("stars_today", r.stars_today >= 0),
        ("full_name", r.full_name == f"{r.owner}/{r.repo}"),
    ]
    # 如果有今日 star 数据，stars_today_str 应非空
    if r.stars_today > 0:
        checks.append(("stars_today_str", bool(r.stars_today_str)))
    for name, passed in checks:
        if passed:
            ok(f"RepoInfo.{name}: {getattr(r, name)!r}")
        else:
            fail(f"RepoInfo.{name} 异常: {getattr(r, name)!r}")

    # 验证缓存二次查询
    t0 = time.time()
    repos2 = await fetcher.fetch("daily")
    t1 = time.time()
    if t1 - t0 < 0.1:  # 从缓存读取应该很快
        ok(f"二次查询命中缓存（耗时 {t1-t0:.4f}s）")
    else:
        skip(f"二次查询耗时 {t1-t0:.2f}s，可能未命中缓存")


# ── Renderer 测试 ─────────────────────────────────────────────────────────


def _make_mock_repos(data_list: list[dict]):
    """将 mock dict 转为 RepoInfo 列表。"""
    from fetcher import RepoInfo

    return [
        RepoInfo(
            rank=d["rank"],
            owner=d["owner"],
            repo=d["repo"],
            url=d["url"],
            description=d.get("description", ""),
            language=d.get("language", ""),
            language_color=d.get("language_color", ""),
            stars=d.get("stars", 0),
            stars_str=d.get("stars_str", "0"),
            stars_today=d.get("stars_today", 0),
            stars_today_str=d.get("stars_today_str", ""),
        )
        for d in data_list
    ]


def test_renderer_basic():
    """测试基本图片渲染。"""
    header("Renderer: 基本渲染")

    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS)

    try:
        image_bytes = render_trending(repos, "daily")
    except Exception as e:
        fail(f"渲染异常: {e}")
        return

    ok(f"生成 {len(image_bytes)} bytes 的 PNG 数据")

    # 验证是有效的 PNG
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        ok(f"图片尺寸: {img.size[0]}×{img.size[1]}, 格式: {img.format}")
    except Exception as e:
        fail(f"无法打开生成的图片: {e}")
        return

    # 验证尺寸合理
    w, h = img.size
    if w == 800:
        ok("宽度 = 800px ✓")
    else:
        fail(f"宽度异常: {w}（预期 800）")

    # 7 个 repo: 7 * 82 + 6*1 = 580, header ~124, footer + padding ~68
    expected_min = 700
    if h > expected_min:
        ok(f"高度 {h}px 合理（7 个项目，预期 > {expected_min}px）")
    else:
        fail(f"高度 {h}px 偏小（预期 > {expected_min}px）")


def test_renderer_edge_cases():
    """测试边界情况：超长名称、空描述、无语言。"""
    header("Renderer: 边界情况")

    from renderer import render_trending

    repos = _make_mock_repos(MOCK_EDGE_CASES)

    try:
        image_bytes = render_trending(repos, "daily")
    except Exception as e:
        fail(f"边界数据渲染异常: {e}")
        return

    ok(f"边界数据渲染成功，{len(image_bytes)} bytes")

    img = PILImage.open(io.BytesIO(image_bytes))
    ok(f"图片尺寸: {img.size[0]}×{img.size[1]}")


def test_renderer_weekly():
    """测试 weekly 模式标题。"""
    header("Renderer: Weekly 模式")

    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS[:3])
    image_bytes = render_trending(repos, "weekly")

    ok(f"Weekly 模式渲染成功，{len(image_bytes)} bytes")


def test_renderer_large_list():
    """测试 25 个项目的大列表。"""
    header("Renderer: 大列表 (25 项)")

    from renderer import render_trending

    # 用 MOCK_REPOS 循环填充到 25 个
    big_list = []
    for i in range(25):
        src = MOCK_REPOS[i % len(MOCK_REPOS)]
        d = {**src, "rank": i + 1}
        big_list.append(d)

    repos = _make_mock_repos(big_list)
    image_bytes = render_trending(repos, "daily")

    img = PILImage.open(io.BytesIO(image_bytes))
    ok(f"25 项渲染: {img.size[0]}×{img.size[1]}, {len(image_bytes)} bytes")

    # 25 项预期高度 > 2000
    if img.size[1] > 2000:
        ok("高度符合预期（25 项 > 2000px）")
    else:
        fail(f"高度异常: {img.size[1]}（预期 > 2000）")


def test_renderer_save_image():
    """将生成的图片保存到磁盘，方便人工检查。"""
    header("Renderer: 保存预览图片")

    from renderer import render_trending

    repos = _make_mock_repos(MOCK_REPOS)
    image_bytes = render_trending(repos, "daily")

    out_path = Path(__file__).parent / "test_preview_daily.png"
    out_path.write_bytes(image_bytes)
    ok(f"预览图已保存: {out_path} ({len(image_bytes):,} bytes)")

    # 也保存 weekly
    image_bytes_w = render_trending(repos, "weekly")
    out_path_w = Path(__file__).parent / "test_preview_weekly.png"
    out_path_w.write_bytes(image_bytes_w)
    ok(f"Weekly 预览图已保存: {out_path_w} ({len(image_bytes_w):,} bytes)")

    # 保存边界情况
    repos_edge = _make_mock_repos(MOCK_EDGE_CASES)
    image_bytes_e = render_trending(repos_edge, "daily")
    out_path_e = Path(__file__).parent / "test_preview_edge.png"
    out_path_e.write_bytes(image_bytes_e)
    ok(f"边界预览图已保存: {out_path_e} ({len(image_bytes_e):,} bytes)")


# ── 集成测试 ──────────────────────────────────────────────────────────────


async def test_integration_full_pipeline():
    """端到端测试：真实数据 → 渲染 → 图片。"""
    header("集成: 完整管线 (真实数据)")

    from fetcher import TrendingFetcher
    from renderer import render_trending

    fetcher = TrendingFetcher()

    try:
        repos = await fetcher.fetch("daily")
    except Exception as e:
        fail(f"数据获取失败: {e}")
        return

    if not repos:
        skip("无数据，跳过渲染")
        return

    ok(f"获取 {len(repos)} 个真实仓库")

    try:
        image_bytes = render_trending(repos, "daily")
    except Exception as e:
        fail(f"渲染失败: {e}")
        return

    # 保存真实数据图片
    out_path = Path(__file__).parent / "test_preview_real.png"
    out_path.write_bytes(image_bytes)
    ok(f"真实数据图片已保存: {out_path} ({len(image_bytes):,} bytes)")

    # 验证图片质量
    img = PILImage.open(io.BytesIO(image_bytes))
    ok(f"图片尺寸: {img.size[0]}×{img.size[1]}, 格式: {img.format}")


# ── 入口 ──────────────────────────────────────────────────────────────────


def print_usage():
    print(__doc__)


async def main():
    args = set(sys.argv[1:])
    quick = "--quick" in args
    fetch_only = "--fetch" in args
    render_only = "--render" in args
    run_all = not (quick or fetch_only or render_only)

    print("GitHub Trending 插件 — 本地测试")
    print(f"Python: {sys.version}")
    print(f"工作目录: {os.getcwd()}")

    # ── 离线测试（始终运行） ──────────────────────────────────────────
    # Renderer 测试（纯离线，用 mock 数据）
    test_renderer_basic()
    test_renderer_edge_cases()
    test_renderer_weekly()
    test_renderer_large_list()
    test_renderer_save_image()

    if render_only:
        ok_all = summary()
        sys.exit(0 if ok_all else 1)

    # ── 联网测试 ──────────────────────────────────────────────────────
    if quick:
        skip("跳过所有联网测试（--quick）")
        summary()
        return

    await test_fetcher_cache()  # 缓存测试无需联网
    await test_fetcher_html_parsing()

    if fetch_only:
        ok_all = summary()
        sys.exit(0 if ok_all else 1)

    # ── 集成测试 ──────────────────────────────────────────────────────
    await test_fetcher_full_flow()
    await test_integration_full_pipeline()

    ok_all = summary()
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    asyncio.run(main())
