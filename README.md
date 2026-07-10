# astrbot_plugin_github_trending

🔥 GitHub Trending 榜单推送插件 for AstrBot。

每日自动获取 GitHub Trending 热门仓库，以排行榜图片形式推送到指定的群聊或私聊。

## ✨ 功能

- **📊 排行榜图片**：深色主题的榜单图片，展示仓库名称、描述、语言、Star 数、今日新增 Star
- **⏰ 定时推送**：每天在设定时间自动推送 GitHub Trending 榜单
- **💬 指令触发**：随时使用 `/trending` 手动获取最新榜单
- **🎯 多目标推送**：支持同时推送到多个群聊或私聊
- **🔌 直接抓取**：直接从 GitHub Trending 页面抓取数据，与网站实时同步
- **🔑 Token 支持**：可配置 GitHub Token 提高请求限额（可选）

## 📦 安装

将插件文件夹放入 AstrBot 的插件目录，安装依赖：

```bash
pip install -r requirements.txt
```

依赖项：
- `beautifulsoup4` — HTML 解析
- `Pillow` — 图片生成
- `aiohttp` — 异步 HTTP 请求

## 🎮 指令参考

| 指令 | 说明 |
|------|------|
| `/trending` | 获取今日 GitHub Trending 榜单 |
| `/trending weekly` | 获取本周 GitHub Trending 榜单 |
| `/trending addhere` | 将当前群聊/私聊加入每日推送列表 |
| `/trending delhere` | 将当前群聊/私聊移出每日推送列表 |
| `/trending list` | 查看所有推送目标 |
| `/trending time 09:00` | 设置每日推送时间（格式 HH:MM） |
| `/trending token ghp_xxx` | 设置 GitHub Personal Access Token |
| `/trending status` | 查看插件当前配置和状态 |

## ⚙️ 配置说明

### 数据来源

插件直接抓取 [GitHub Trending](https://github.com/trending) 页面，数据与网站实时同步，包含排名、描述、语言、总 Star 数和今日新增 Star 数。

### GitHub Token（可选）

不配置 Token 也可正常使用（匿名访问 GitHub Trending 页面）。如果遇到频繁的 429 限流，可配置 Token：

1. 访问 [GitHub Settings → Personal access tokens](https://github.com/settings/tokens)
2. 生成一个 classic token，无需勾选任何 scope
3. 在私聊中使用 `/trending token ghp_xxxxxxxxxxxx` 配置

### 推送目标

在需要接收每日推送的群聊或私聊中发送 `/trending addhere` 即可添加。

### 推送时间

默认每天 **09:00** 推送，使用 `/trending time HH:MM` 修改。

## 📸 效果预览

生成的图片样式：

```
┌──────────────────────────────────────────┐
│       🔥 GitHub Trending — Daily         │
│          2026-07-10 周四                 │
│                                          │
│  🥇  owner/repo-name          ⭐ 52.3k  │
│      A short description of the project  │
│      🔴 Python        🔥 +2.3k today    │
│  ─────────────────────────────────────  │
│  🥈  owner/repo-name          ⭐ 38.1k  │
│      Description text here...           │
│      🟢 JavaScript      🔥 +1.8k today  │
│  ─────────────────────────────────────  │
│  #4  owner/repo-name          ⭐ 12.3k  │
│      Description text...               │
│      🟣 Rust            🔥 +856 today   │
│  ─────────────────────────────────────  │
│  ...                                     │
└──────────────────────────────────────────┘
```

## 🛠️ 开发

项目结构：

```
├── main.py          # 插件入口：指令处理、定时任务、消息发送
├── fetcher.py       # 数据层：GitHub Trending 页面抓取 + HTML 解析 + 缓存
├── renderer.py      # 渲染层：Pillow 排行榜图片生成
├── test_local.py    # 本地测试：fetcher + renderer（无需 AstrBot）
├── metadata.yaml    # 插件元数据
└── requirements.txt # 依赖清单
```

## 📄 License

MIT
