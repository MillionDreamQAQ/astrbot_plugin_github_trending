# GitHub Trending AstrBot Plugin

> 状态: ✅ 已实现 | 更新: 2026-07-10

## Architecture

```
main.py          — 插件入口（9 命令 + asyncio 定时 + KV 配置）
fetcher.py       — 数据层（抓取 github.com/trending → BS4 解析 → 翻译 → 缓存）
renderer.py      — 渲染层（2x Pillow 高清渲染，手绘图标，零 emoji 依赖）
translator.py    — 翻译（Google 免费接口，批量翻译 + 缓存）
test_local.py    — 测试套件（64 项：fetcher / renderer / translator）
```

## Data Flow

```
github.com/trending ─→ BS4 parse ─→ translate (opt) ─→ cache (5min)
                                                              │
                                              Pillow 2x render ─→ base64 ─→ send
```

## Commands

`/trending [weekly|addhere|delhere|list|time|lang|token|status]`

## Key Features

| 功能 | 实现 |
|------|------|
| 数据来源 | 直接抓取 GitHub Trending，与网站实时同步 |
| 图片清晰度 | 2x 缩放 1600px，144 DPI 元数据 |
| 图标 | Pillow 手绘（五角星、三角），不依赖 emoji 字体 |
| 翻译 | Google 免费接口，批量翻译，静默降级 |
| 存储 | AstrBot KV Store |
| 调度 | asyncio.create_task 循环 |
| 发送 | Image.fromBase64() 消息链 |

## Dependencies

```
beautifulsoup4  — HTML 解析
Pillow          — 图片渲染
aiohttp         — HTTP 请求
```
