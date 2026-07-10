"""GitHub Trending 图片渲染器。

使用 Pillow 生成排行榜风格的列表图片。
所有图标用 Pillow 原生绘制，不依赖 emoji 字体。
支持 2x 缩放渲染，在高 DPI 屏幕上更清晰。
"""
from __future__ import annotations

import io
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

try:
    from .fetcher import RepoInfo
except ImportError:
    from fetcher import RepoInfo

# ── 渲染倍率 ──────────────────────────────────────────────────────────────
SCALE = 2  # 2x 渲染：1600px 宽，在高 DPI 屏幕（手机/Retina）上更清晰

# ── 配色 (GitHub Dark 风格) ──────────────────────────────────────────────
BG_COLOR = "#0d1117"
CARD_BG = "#161b22"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_TERTIARY = "#6e7681"
ACCENT_GOLD = "#f0c040"
ACCENT_SILVER = "#b0b8c0"
ACCENT_BRONZE = "#d4845a"
ACCENT_ORANGE = "#f78166"

# 布局基准值（实际渲染时 × SCALE）
_BW = 800              # 画布宽度
_BPX = 40               # 水平内边距
_BPT = 32               # 顶部内边距
_BPB = 24               # 底部内边距
_BHH = 80               # 头部高度
_BIH = 82               # 单个项目高度
_BSH = 1                # 项目间分隔线宽度
_BFH = 66               # 底部高度
_BRS = 44               # 排名徽章尺寸
_BRR = 8                # 普通排名圆角半径
_BSP = 12               # 头部与列表间距
_BGS = 8                # 行内小间距

# 图标基准尺寸
_STAR_R = 7             # 五角星半径
_TRI_SIZE = 8           # 三角图标尺寸
_DOT_R = 5              # 语言圆点半径

# ── 字体查找 ──────────────────────────────────────────────────────────────

_FONT_CANDIDATES = [
    "msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "simsun.ttf",  # Windows
    "PingFang.ttc", "Heiti SC.ttf", "STHeiti.ttf",                       # macOS
    "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc",                   # Linux
    "NotoSansSC-Regular.otf", "wqy-microhei.ttc", "wqy-zenhei.ttc",
    "DroidSansFallbackFull.ttf",
    "DejaVuSans.ttf", "arial.ttf",
]


def _search_font_paths() -> list[Path]:
    candidates: list[Path] = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        candidates.append(Path(windir) / "Fonts")
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        candidates.extend([Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"])
    else:
        candidates.extend([Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts", Path.home() / ".local" / "share" / "fonts"])
    return candidates


def find_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    for base in _search_font_paths():
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower() == font_name.lower():
                    try:
                        return ImageFont.truetype(str(Path(root) / f), size)
                    except OSError:
                        continue
    for name in _FONT_CANDIDATES:
        for base in _search_font_paths():
            for root, _dirs, files in os.walk(base):
                if name.lower() in (fn.lower() for fn in files):
                    for f in files:
                        if f.lower() == name.lower():
                            try:
                                return ImageFont.truetype(str(Path(root) / f), size)
                            except OSError:
                                continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


# ── 工具 ──────────────────────────────────────────────────────────────────


def _truncate_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if not text:
        return ""
    bbox = font.getbbox(text)
    if bbox[2] - bbox[0] <= max_width:
        return text
    while len(text) > 0:
        text = text[:-1]
        if font.getbbox(text + "...")[2] - font.getbbox(text + "...")[0] <= max_width:
            return text + "..."
    return "..."


def _get_medal_info(rank: int) -> tuple[str, str, str]:
    if rank == 1:
        return ACCENT_GOLD, "#0d1117", "1"
    elif rank == 2:
        return ACCENT_SILVER, "#0d1117", "2"
    elif rank == 3:
        return ACCENT_BRONZE, "#0d1117", "3"
    else:
        return CARD_BG, TEXT_SECONDARY, str(rank)


def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill: str):
    points = []
    for i in range(5):
        outer = i * 4 * math.pi / 5 - math.pi / 2
        inner = outer + 2 * math.pi / 10
        points.append((cx + r * math.cos(outer), cy + r * math.sin(outer)))
        points.append((cx + r * 0.38 * math.cos(inner), cy + r * 0.38 * math.sin(inner)))
    draw.polygon(points, fill=fill)


def _draw_triangle_up(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, fill: str):
    draw.polygon([(x + size / 2, y), (x, y + size), (x + size, y + size)], fill=fill)


# ── 主渲染 ────────────────────────────────────────────────────────────────


def render_trending(
    repos: list[RepoInfo],
    feed_type: str = "daily",
) -> bytes:
    """将 trending 数据渲染为高清 PNG 图片（2x 缩放）。

    Args:
        repos: RepoInfo 列表
        feed_type: "daily" 或 "weekly"

    Returns:
        PNG 图片的 bytes
    """
    s = SCALE  # 简写

    # ── 缩放后的布局参数 ─────────────────────────────────────────────
    W = _BW * s
    PX = _BPX * s
    PT = _BPT * s
    PB = _BPB * s
    HH = _BHH * s
    IH = _BIH * s
    SH = _BSH  # 分隔线保持 1px
    FH = _BFH * s
    RS = _BRS * s
    BR = _BRR * s
    SP = _BSP * s
    GS = _BGS * s
    # 图标
    STAR_R = _STAR_R * s
    TRI_SIZE = _TRI_SIZE * s
    DOT_R = _DOT_R * s

    # ── 字体（字号 × SCALE）───────────────────────────────────────────
    font_title = find_font("msyh.ttc", 28 * s)
    font_title_en = find_font("msyh.ttc", 24 * s)
    font_name = find_font("msyh.ttc", 18 * s)
    font_desc = find_font("msyh.ttc", 15 * s)
    font_lang = find_font("msyh.ttc", 14 * s)
    font_stars = find_font("msyh.ttc", 16 * s)
    font_rank = find_font("msyh.ttc", 22 * s)
    font_footer = find_font("msyh.ttc", 14 * s)
    font_date = find_font("msyh.ttc", 15 * s)

    # ── 画布 ─────────────────────────────────────────────────────────
    item_count = len(repos)
    content_h = item_count * IH + (item_count - 1) * SH
    total_h = PT + HH + content_h + FH + PB
    img = Image.new("RGB", (W, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PT

    # ── 头部 ─────────────────────────────────────────────────────────
    draw.text((PX, y), "GitHub Trending", fill="#f0c040", font=font_title_en)
    subtitle = "— Daily" if feed_type == "daily" else "— Weekly"
    tw = draw.textbbox((0, 0), "GitHub Trending", font=font_title_en)[2]
    draw.text((PX + tw + GS, y + 4 * s), subtitle, fill=TEXT_SECONDARY, font=font_title_en)

    now = datetime.now()
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_str = now.strftime(f"%Y-%m-%d {weekday_map[now.weekday()]}")
    draw.text((PX, y + 38 * s), date_str, fill=TEXT_TERTIARY, font=font_date)

    y += HH
    draw.line([(PX, y), (W - PX, y)], fill=CARD_BG, width=1)
    y += SP

    # ── 项目列表 ─────────────────────────────────────────────────────
    name_max_w = W - PX * 2 - RS - 16 * s - 120 * s

    for repo in repos:
        rank = repo.rank
        cleft, cright = PX, W - PX

        # 排名徽章
        badge_bg, badge_fg, badge_text = _get_medal_info(rank)
        bx, by = cleft, y + (IH - RS) // 2
        if rank <= 3:
            draw.ellipse([(bx, by), (bx + RS, by + RS)], fill=badge_bg)
        else:
            draw.rounded_rectangle([(bx, by), (bx + RS, by + RS)], radius=BR, fill=badge_bg)

        rw = draw.textbbox((0, 0), badge_text, font=font_rank)[2]
        rh = draw.textbbox((0, 0), badge_text, font=font_rank)[3] - draw.textbbox((0, 0), badge_text, font=font_rank)[1]
        draw.text(
            (bx + (RS - rw) / 2, by + (RS - rh) / 2 - 6 * s),
            badge_text, fill=badge_fg, font=font_rank,
        )

        # 仓库名
        nx, ny = bx + RS + 16 * s, y + 8 * s
        name_disp = _truncate_text(repo.full_name, font_name, name_max_w)
        draw.text((nx, ny), name_disp, fill=TEXT_PRIMARY, font=font_name)

        # 总 Star（右对齐）
        stars_text = repo.stars_str
        sw = draw.textbbox((0, 0), stars_text, font=font_stars)[2]
        sx = cright - sw - STAR_R * 2 - 6 * s
        sy = ny + 8 * s
        _draw_star(draw, sx + STAR_R, sy + STAR_R, STAR_R, ACCENT_ORANGE)
        draw.text((cright - sw, ny), stars_text, fill=ACCENT_ORANGE, font=font_stars)

        # 描述
        dy = ny + 28 * s
        if repo.description:
            desc_disp = _truncate_text(repo.description, font_desc, cright - nx)
            draw.text((nx, dy), desc_disp, fill=TEXT_SECONDARY, font=font_desc)

        # 语言 + 今日 Star
        ly = dy + 24 * s
        if repo.language:
            dx, dy2 = nx, ly + 6 * s
            draw.ellipse([(dx, dy2), (dx + DOT_R * 2, dy2 + DOT_R * 2)], fill=repo.language_color)
            draw.text((nx + 16 * s, ly), repo.language, fill=TEXT_TERTIARY, font=font_lang)

        if repo.stars_today > 0:
            today_text = f"+{repo.stars_today_str} today"
            tw2 = draw.textbbox((0, 0), today_text, font=font_lang)[2]
            tx = cright - tw2 - TRI_SIZE - 5 * s
            ty = ly + 5 * s
            _draw_triangle_up(draw, tx, ty, TRI_SIZE, ACCENT_ORANGE)
            draw.text((cright - tw2, ly), today_text, fill=ACCENT_ORANGE, font=font_lang)

        y += IH
        if rank < item_count:
            draw.line([(cleft, y), (cright, y)], fill=CARD_BG, width=SH)

    y += 8 * s

    # ── 底部 ─────────────────────────────────────────────────────────
    trending_url = (
        "https://github.com/trending?since=daily"
        if feed_type == "daily" else "https://github.com/trending?since=weekly"
    )
    footer_text = f"共 {item_count} 个项目 · 数据来自 GitHub Trending · 每日更新"
    fw = draw.textbbox((0, 0), footer_text, font=font_footer)[2]
    draw.text(((W - fw) / 2, y), footer_text, fill=TEXT_TERTIARY, font=font_footer)
    y += 22 * s
    uw = draw.textbbox((0, 0), trending_url, font=font_footer)[2]
    draw.text(((W - uw) / 2, y), trending_url, fill="#58a6ff", font=font_footer)

    # ── 导出（带 DPI 元数据）─────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, dpi=(144, 144))
    return buf.getvalue()
