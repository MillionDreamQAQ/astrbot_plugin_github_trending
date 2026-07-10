# GitHub Trending AstrBot Plugin — Implementation Plan

## Context

Build an AstrBot plugin that fetches GitHub trending repositories daily, renders them as a leaderboard-style image, and pushes to configured chat groups/users via commands. The user has an RSS feed (`https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml`) but it only provides repo names + links — lacks stars, language, etc., so we enrich via GitHub API.

## Requirements Summary

- **Image style**: Ranked leaderboard list (🥇🥈🥉 for top 3, then #4-#25)
- **Config**: Via chat commands (`/trending addhere`, `/trending delhere`, etc.)
- **Language filter**: Not needed for v1
- **Delivery**: Daily scheduled push + manual `/trending` command

## Architecture

```
main.py  (plugin entry, commands, scheduler)
├── fetcher.py     — RSS parse + GitHub API enrichment + cache
├── renderer.py    — Pillow image generation (leaderboard list)
└── metadata.yaml  — plugin metadata
```

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `main.py` | Rewrite | Plugin class, 8 commands, scheduler loop |
| `fetcher.py` | Create | Data layer: RSS + GitHub API |
| `renderer.py` | Create | Pillow-based leaderboard image |
| `metadata.yaml` | Update | Plugin name, desc, author |
| `requirements.txt` | Create | Dependencies |
| `README.md` | Update | Usage docs |

## Data Flow

```
RSS Feed ──→ repo list (name, link)
                │
                ▼
         GitHub API (per repo) ──→ stars, language, description
                │
                ▼
         Cache in memory (5 min TTL, avoid API rate limits)
                │
                ▼
         Pillow Renderer ──→ PNG bytes (base64)
                │
                ▼
         Send via event.image_result() or context.send_message()
```

## Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/trending` | `daily_trending` | Fetch & return daily trending image |
| `/trending weekly` | `weekly_trending` | Fetch & return weekly trending image |
| `/trending addhere` | `add_target` | Add current group/user to daily push list |
| `/trending delhere` | `del_target` | Remove current group/user from push list |
| `/trending list` | `list_targets` | Show all configured push targets |
| `/trending time HH:MM` | `set_time` | Set daily push time (admin only) |
| `/trending token <ghp_xxx>` | `set_token` | Set GitHub API token |
| `/trending status` | `status` | Show full config (push time, targets, token set or not) |

## Image Design (Ranked Leaderboard)

```
┌──────────────────────────────────────────┐
│       🔥 GitHub Trending — Daily         │
│          2026-07-10 周四                 │
│                                          │
│  🥇  owner/repo-name          ⭐ 52.3k  │
│      A short description of the project  │
│      🔴 Python                          │
│  ─────────────────────────────────────  │
│  🥈  owner/repo-name          ⭐ 38.1k  │
│      Description text here...           │
│      🟢 JavaScript                      │
│  ─────────────────────────────────────  │
│  🥉  owner/repo-name          ⭐ 21.7k  │
│      Description text here...           │
│      🟡 TypeScript                      │
│  ─────────────────────────────────────  │
│  #4  owner/repo-name          ⭐ 12.3k  │
│      Description text...               │
│      🟣 Rust                            │
│  ─────────────────────────────────────  │
│  ... (up to 25 items)                   │
│                                          │
│   共 25 个项目 · GitHub Trending · 每   │
│              日更新                      │
└──────────────────────────────────────────┘
```

- Width: 800px, height dynamic based on item count
- Background: dark (#1a1b27) with light text for a terminal/tech feel
- Top 3: medal emoji + gold/silver/bronze accent
- Language colors: standard GitHub language colors
- Star count: right-aligned with ⭐ icon
- Each item takes ~80px height × 800px width

## Scheduling

Use `asyncio.create_task` with a loop (Pattern A from AstrBot ecosystem):
- Calculate time until next `push_time` (default 09:00)
- Sleep, then push, then wait 60s to avoid double-fire
- Recalculate for next day

## Config Storage

Use AstrBot KV store (`self.put_kv_data` / `self.get_kv_data`):

```json
{
  "targets": ["qq:group:123456", "qq:friend:789012"],
  "push_time": "09:00",
  "github_token": "",
  "daily_enabled": true
}
```

## Key Dependencies

```
feedparser>=6.0.0      # RSS parsing
Pillow>=10.0.0          # Image generation
aiohttp>=3.8.0          # Async GitHub API calls
```

No APScheduler needed — asyncio.create_task loop is sufficient for a single daily job.

## Verification

1. **RSS parsing**: Run fetcher, verify 25 repos returned with valid names/links
2. **GitHub API**: Run fetcher with enrichment, verify stars/language populated
3. **Image generation**: Generate image, verify readable text and layout
4. **Commands**: Test `/trending`, `/trending addhere`, `/trending list`, `/trending time`
5. **Scheduling**: Set time 1 min ahead, verify push fires
6. **Edge cases**: GitHub API rate limited → graceful fallback (show what we have); RSS unavailable → error message; empty target list → reminder to add targets
