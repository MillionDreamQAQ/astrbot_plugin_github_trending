# GitHub Trending AstrBot Plugin

> Phase 1: ✅ 已完成 | Phase 2: 📋 计划中 | 更新: 2026-07-10

## Architecture

```
main.py          — 插件入口（12 命令 + asyncio 定时 + KV 配置 + 诊断）
fetcher.py       — 数据层（github.com/trending → BS4 → 翻译 → 缓存）
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

## Commands（12 个）

`/trending [help|weekly|addhere|delhere|list|time|lang|proxy|language|community|token|debug|status]`

## Key Features

| 功能 | 实现 |
|------|------|
| 数据来源 | 直接抓取 GitHub Trending 页面，与网站实时同步 |
| 语言过滤 | 编程语言 + 社区口语两层过滤，可组合 |
| 图片清晰度 | 2x 缩放 1600px，144 DPI 元数据 |
| 图标 | Pillow 手绘（五角星、三角），零 emoji 字体依赖 |
| 翻译 | Google 免费接口，批量翻译 + 缓存，失败降级保留原文 |
| 代理 | 支持 HTTP/HTTPS/SOCKS5，解决国内网络问题 |
| 诊断 | `/trending debug` 逐项检查网络/解析/翻译/代理 |
| 存储 | AstrBot KV Store |
| 调度 | asyncio.create_task 循环 |

## Roadmap — Phase 2 📋

**独立订阅系统**（计划下周实施）：

| 功能 | 说明 |
|------|------|
| 独立定时 | 每个订阅独立的推送时间 |
| 独立过滤 | 每个订阅独立的语言/社区设置 |
| 多订阅 | 同一群可创建多个订阅（如全球 + 中文社区） |
| 订阅管理 | `/trending sub <id>` 开关/修改订阅 |

数据模型：`targets[]` → `subscriptions[]`（含 id、umo、push_time、language、spoken_language、enabled）。自动迁移旧数据。

## Troubleshooting

- `/trending debug` — 一键诊断网络、抓取、解析、翻译、代理
- 国内服务器无法访问 Google API → 配置代理
- 翻译失败有日志，不再静默吞异常

## Dependencies

```
beautifulsoup4  — HTML 解析
Pillow          — 图片渲染
aiohttp         — HTTP 请求
```


