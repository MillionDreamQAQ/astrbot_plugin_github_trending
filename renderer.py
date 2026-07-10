"""GitHub Trending 图片渲染器。

使用 Pillow 生成排行榜风格的列表图片。
所有图标用 Pillow 原生绘制，不依赖 emoji 字体。
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

# ── 配色 (GitHub Dark 风格) ────────────────────────────────────────────
BG_COLOR = "#0d1117"  # 主背景
CARD_BG = "#161b22"  # 卡片 / 分隔线色
TEXT_PRIMARY = "#e6edf3"  # 主文字
TEXT_SECONDARY = "#8b949e"  # 次要文字
TEXT_TERTIARY = "#6e7681"  # 更淡的文字
ACCENT_GOLD = "#f0c040"
ACCENT_SILVER = "#b0b8c0"
ACCENT_BRONZE = "#d4845a"
ACCENT_ORANGE = "#f78166"  # stars / 热度

# 布局参数
IMG_WIDTH = 800
IMG_PADDING_X = 40
IMG_PADDING_TOP = 32
IMG_PADDING_BOTTOM = 24
HEADER_HEIGHT = 80
ITEM_HEIGHT = 82
ITEM_SEPARATOR_HEIGHT = 1
FOOTER_HEIGHT = 66
RANK_SIZE = 44  # 排名徽章尺寸

# ── 字体查找 ───────────────────────────────────────────────────────────

# 备选字体列表（优先级从高到低）
_FONT_CANDIDATES = [
    # Windows
    "msyh.ttc",  # 微软雅黑
    "msyhbd.ttc",
    "simhei.ttf",
    "simsun.ttc",
    "simsun.ttf",
    # macOS
    "PingFang.ttc",
    "Heiti SC.ttf",
    "STHeiti.ttf",
    # Linux
    "NotoSansCJK-Regular.ttc",
    "NotoSansCJK-Bold.ttc",
    "NotoSansSC-Regular.otf",
    "wqy-microhei.ttc",
    "wqy-zenhei.ttc",
    "DroidSansFallbackFull.ttf",
    # Generic
    "DejaVuSans.ttf",
    "arial.ttf",
]


def _search_font_paths() -> list[Path]:
    """收集系统上所有可能的字体目录。"""
    candidates: list[Path] = []

    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        candidates.append(Path(windir) / "Fonts")
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts",
            ]
        )
    else:
        candidates.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
                Path.home() / ".local" / "share" / "fonts",
            ]
        )

    return candidates


def find_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """查找可用字体，找不到则回退到 PIL 默认字体。"""
    # 先尝试直接按名称加载
    for base in _search_font_paths():
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower() == font_name.lower():
                    try:
                        return ImageFont.truetype(str(Path(root) / f), size)
                    except OSError:
                        continue

    # 遍历备选列表，找到任意可用的
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

    # 最终回退：PIL 默认字体（不支持 CJK）
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


# ── 工具函数 ───────────────────────────────────────────────────────────


def _truncate_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """按像素宽度截断文本，超出部分加 ..."""
    if not text:
        return ""
    # 快速路径
    bbox = font.getbbox(text)
    if bbox[2] - bbox[0] <= max_width:
        return text
    # 逐字缩减
    ellipsis = "..."
    while len(text) > 0:
        text = text[:-1]
        bbox = font.getbbox(text + ellipsis)
        if bbox[2] - bbox[0] <= max_width:
            return text + ellipsis
    return ellipsis


def _get_medal_info(rank: int) -> tuple[str, str, str]:
    """根据排名返回 (徽章背景色, 文字色, 显示文本)。"""
    if rank == 1:
        return ACCENT_GOLD, "#0d1117", "1"
    elif rank == 2:
        return ACCENT_SILVER, "#0d1117", "2"
    elif rank == 3:
        return ACCENT_BRONZE, "#0d1117", "3"
    else:
        return CARD_BG, TEXT_SECONDARY, str(rank)


def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill: str):
    """在 (cx, cy) 画一个五角星（纯 Pillow 绘制，无需 emoji 字体）。"""
    points = []
    for i in range(5):
        outer_angle = i * 4 * math.pi / 5 - math.pi / 2
        inner_angle = outer_angle + 2 * math.pi / 10
        points.append((cx + r * math.cos(outer_angle), cy + r * math.sin(outer_angle)))
        points.append((cx + r * 0.38 * math.cos(inner_angle), cy + r * 0.38 * math.sin(inner_angle)))
    draw.polygon(points, fill=fill)


def _draw_triangle_up(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, fill: str):
    """在 (x, y) 为左上角画一个向上的小三角。"""
    draw.polygon(
        [(x + size / 2, y), (x, y + size), (x + size, y + size)],
        fill=fill,
    )


# ── 主渲染函数 ─────────────────────────────────────────────────────────


def render_trending(
    repos: list[RepoInfo],
    feed_type: str = "daily",
) -> bytes:
    """将 trending 数据渲染为 PNG 图片。

    Args:
        repos: RepoInfo 列表
        feed_type: "daily" 或 "weekly"

    Returns:
        PNG 图片的 bytes
    """
    # ── 字体 ─────────────────────────────────────────────────────────
    font_title = find_font("msyh.ttc", 28)
    font_title_en = find_font("arial.ttf", 24)
    font_subtitle = find_font("msyh.ttc", 16)
    font_name = find_font("msyh.ttc", 18)  # owner/repo 名称（加粗后备）
    font_desc = find_font("msyh.ttc", 15)
    font_lang = find_font("msyh.ttc", 14)
    font_stars = find_font("msyh.ttc", 16)
    font_rank = find_font("msyh.ttc", 22)
    font_footer = find_font("msyh.ttc", 14)
    font_date = find_font("msyh.ttc", 15)

    # ── 计算画布高度 ─────────────────────────────────────────────────
    item_count = len(repos)
    content_height = (
        item_count * ITEM_HEIGHT
        + (item_count - 1) * ITEM_SEPARATOR_HEIGHT
    )
    total_height = IMG_PADDING_TOP + HEADER_HEIGHT + content_height + FOOTER_HEIGHT + IMG_PADDING_BOTTOM

    # ── 创建画布 ─────────────────────────────────────────────────────
    img = Image.new("RGB", (IMG_WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = IMG_PADDING_TOP

    # ── 头部 ─────────────────────────────────────────────────────────
    title_text = "GitHub Trending"
    sub_text = "— Daily" if feed_type == "daily" else "— Weekly"

    # 主标题
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title_en)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        (IMG_PADDING_X, y),
        title_text,
        fill="#f0c040",
        font=font_title_en,
    )

    # 副标题
    sub_x = IMG_PADDING_X + title_w + 8
    draw.text(
        (sub_x, y + 4),
        sub_text,
        fill=TEXT_SECONDARY,
        font=font_title_en,
    )

    # 日期
    now = datetime.now()
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[now.weekday()]
    date_str = now.strftime(f"%Y-%m-%d {weekday}")
    draw.text(
        (IMG_PADDING_X, y + 38),
        date_str,
        fill=TEXT_TERTIARY,
        font=font_date,
    )

    y += HEADER_HEIGHT

    # ── 分隔线 ───────────────────────────────────────────────────────
    y_sep = y
    draw.line(
        [(IMG_PADDING_X, y_sep), (IMG_WIDTH - IMG_PADDING_X, y_sep)],
        fill=CARD_BG,
        width=1,
    )
    y += 12

    # ── 项目列表 ─────────────────────────────────────────────────────
    repo_name_max_w = IMG_WIDTH - IMG_PADDING_X * 2 - RANK_SIZE - 16 - 120

    for repo in repos:
        rank = repo.rank
        card_left = IMG_PADDING_X
        card_right = IMG_WIDTH - IMG_PADDING_X

        # ── 排名徽章 ──────────────────────────────────────────────
        badge_bg, badge_fg, badge_text = _get_medal_info(rank)
        badge_x = card_left
        badge_y = y + (ITEM_HEIGHT - RANK_SIZE) // 2

        # 根据排名是否有特殊背景
        if rank <= 3:
            draw.ellipse(
                [
                    (badge_x, badge_y),
                    (badge_x + RANK_SIZE, badge_y + RANK_SIZE),
                ],
                fill=badge_bg,
            )
        else:
            # 普通排名用圆角矩形
            draw.rounded_rectangle(
                [
                    (badge_x, badge_y),
                    (badge_x + RANK_SIZE, badge_y + RANK_SIZE),
                ],
                radius=8,
                fill=badge_bg,
            )

        # 排名数字
        rank_bbox = draw.textbbox((0, 0), badge_text, font=font_rank)
        rank_w = rank_bbox[2] - rank_bbox[0]
        rank_h = rank_bbox[3] - rank_bbox[1]
        draw.text(
            (badge_x + (RANK_SIZE - rank_w) / 2, badge_y + (RANK_SIZE - rank_h) / 2 - 2),
            badge_text,
            fill=badge_fg,
            font=font_rank,
        )

        # ── 仓库名称 ──────────────────────────────────────────────
        name_x = badge_x + RANK_SIZE + 16
        name_y = y + 8
        full_name = repo.full_name

        # 截断过长名称
        name_display = _truncate_text(full_name, font_name, repo_name_max_w)
        draw.text((name_x, name_y), name_display, fill=TEXT_PRIMARY, font=font_name)

        # ── Star 数（右对齐，五角星图标 + 数字） ──────────────────
        stars_text = repo.stars_str
        stars_bbox = draw.textbbox((0, 0), stars_text, font=font_stars)
        stars_w = stars_bbox[2] - stars_bbox[0]
        star_icon_r = 7
        star_icon_x = card_right - stars_w - star_icon_r * 2 - 6
        star_icon_y = name_y + 8
        _draw_star(draw, star_icon_x + star_icon_r, star_icon_y + star_icon_r, star_icon_r, ACCENT_ORANGE)
        draw.text(
            (card_right - stars_w, name_y),
            stars_text,
            fill=ACCENT_ORANGE,
            font=font_stars,
        )

        # ── 描述 ──────────────────────────────────────────────────
        desc_y = name_y + 28
        if repo.description:
            desc_display = _truncate_text(
                repo.description, font_desc, card_right - name_x
            )
            draw.text(
                (name_x, desc_y),
                desc_display,
                fill=TEXT_SECONDARY,
                font=font_desc,
            )

        # ── 语言 + 今日 Star ──────────────────────────────────────
        lang_y = desc_y + 24
        if repo.language:
            # 语言颜色圆点
            dot_r = 5
            dot_x = name_x
            dot_y = lang_y + 6
            draw.ellipse(
                [(dot_x, dot_y), (dot_x + dot_r * 2, dot_y + dot_r * 2)],
                fill=repo.language_color,
            )
            # 语言名称
            draw.text(
                (name_x + 16, lang_y),
                repo.language,
                fill=TEXT_TERTIARY,
                font=font_lang,
            )

        # 今日新增 star（右对齐，三角图标 + 文本）
        if repo.stars_today > 0:
            today_text = f"+{repo.stars_today_str} today"
            today_bbox = draw.textbbox((0, 0), today_text, font=font_lang)
            today_w = today_bbox[2] - today_bbox[0]
            tri_size = 8
            tri_x = card_right - today_w - tri_size - 5
            tri_y = lang_y + 5
            _draw_triangle_up(draw, tri_x, tri_y, tri_size, ACCENT_ORANGE)
            draw.text(
                (card_right - today_w, lang_y),
                today_text,
                fill=ACCENT_ORANGE,
                font=font_lang,
            )

        # ── 项目间分隔线 ──────────────────────────────────────────
        y += ITEM_HEIGHT
        if rank < item_count:
            sep_y = y
            draw.line(
                [(card_left, sep_y), (card_right, sep_y)],
                fill=CARD_BG,
                width=ITEM_SEPARATOR_HEIGHT,
            )

    y += 8

    # ── 底部 ─────────────────────────────────────────────────────────
    trending_url = (
        "https://github.com/trending?since=daily"
        if feed_type == "daily"
        else "https://github.com/trending?since=weekly"
    )

    footer_text = f"共 {item_count} 个项目 · 数据来自 GitHub Trending · 每日更新"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_w = footer_bbox[2] - footer_bbox[0]
    draw.text(
        ((IMG_WIDTH - footer_w) / 2, y),
        footer_text,
        fill=TEXT_TERTIARY,
        font=font_footer,
    )

    # 链接行
    y += 22
    url_bbox = draw.textbbox((0, 0), trending_url, font=font_footer)
    url_w = url_bbox[2] - url_bbox[0]
    draw.text(
        ((IMG_WIDTH - url_w) / 2, y),
        trending_url,
        fill="#58a6ff",  # GitHub 链接蓝
        font=font_footer,
    )

    # ── 导出字节 ─────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
