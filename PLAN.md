# GitHub Trending AstrBot Plugin

> 状态: ✅ 已实现 | 更新: 2026-07-10

## Architecture

```
main.py          — 插件入口（10 命令 + asyncio 定时 + KV 配置 + 诊断）
fetcher.py       — 数据层（github.com/trending → BS4 → 翻译 → 缓存 + 详细错误）
renderer.py      — 渲染层（2x 1600px，手绘图标，零 emoji 依赖）
translator.py    — 翻译（Google 免费接口，批量 + 缓存 + 日志）
test_local.py    — 测试套件（64 项：fetcher / renderer / translator）
```

## Data Flow

```
github.com/trending ─→ BS4 parse ─→ translate (opt) ─→ cache (5min)
                                                              │
                                              Pillow 2x render ─→ base64 ─→ send
                                                              │
                                      文字链接（榜单URL + Top5直达）
```

## Commands

`/trending [weekly|addhere|delhere|list|time|lang|proxy|token|debug|status]`

## Key Features

| 功能 | 实现 |
|------|------|
| 数据来源 | 直接抓取 GitHub Trending 页面，与网站实时同步 |
| 图片清晰度 | 2x 缩放 1600px，144 DPI 元数据 |
| 图标 | Pillow 手绘（五角星、三角），零 emoji 字体依赖 |
| 翻译 | Google 免费接口，批量翻译 + 缓存，失败降级保留原文 |
| 代理 | 支持 HTTP/HTTPS/SOCKS5，解决国内网络问题 |
| 诊断 | `/trending debug` 逐项检查网络/解析/翻译/代理 |
| 存储 | AstrBot KV Store |
| 调度 | asyncio.create_task 循环 |

## Troubleshooting

- `/trending debug` — 一键诊断网络、抓取、解析、翻译、代理状态
- 国内服务器无法访问 Google API → 配置代理 `proxy http://x.x.x.x:port`
- 翻译失败有日志（`logger.warning`），不再静默吞异常

## Dependencies

```
beautifulsoup4  — HTML 解析
Pillow          — 图片渲染
aiohttp         — HTTP 请求（抓取 + 翻译均用此）
```

