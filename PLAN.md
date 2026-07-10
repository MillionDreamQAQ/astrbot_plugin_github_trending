# GitHub Trending AstrBot Plugin — Implementation Plan

> 最后更新: 2026-07-10 | 状态: ✅ 已实现

## Architecture (Actual)

```
main.py  (plugin entry, commands, scheduler)
├── fetcher.py     — GitHub Trending page scraping + HTML parsing + cache
├── renderer.py    — Pillow image generation (leaderboard list)
└── metadata.yaml  — plugin metadata
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Plugin class, 8 commands, asyncio scheduler loop, KV config |
| `fetcher.py` | Scrape `github.com/trending`, parse with BeautifulSoup, 5min cache |
| `renderer.py` | Dark theme leaderboard PNG, top 3 medals, language dots, stars today |
| `test_local.py` | Offline + online tests for fetcher and renderer |
| `metadata.yaml` | Plugin metadata |
| `requirements.txt` | beautifulsoup4, Pillow, aiohttp |

## Data Flow (Final)

```
github.com/trending?since=daily ──→ BeautifulSoup parse ──→ RepoInfo list
                                                                    │
                                              Cache (5 min TTL) ←──┘
                                                                    │
                                              Pillow Renderer ←─────┘
                                                                    │
                                              image bytes (base64) ─→ send
```

## Key Design Decisions

- **直接抓取** 替代 RSS+API：数据实时一致，一个请求拿全部，还多了今日新增 Star
- **BeautifulSoup** 而非正则：更健壮地应对 HTML 结构变化
- **asyncio.create_task** 而非 APScheduler：单一定时任务，省依赖
- **Image.fromBase64()** 而非 image_result()：bytes 图片必须转 base64 通过消息链发送
- **try/except ImportError** 兼容 AstrBot 包内导入和本地独立测试

## Dependencies

```
beautifulsoup4>=4.12.0    # HTML parsing
Pillow>=10.0.0             # Image generation
aiohttp>=3.8.0             # Async HTTP
```
