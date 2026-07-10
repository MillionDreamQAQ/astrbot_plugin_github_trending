# astrbot_plugin_github_trending

🔥 GitHub Trending 榜单推送插件 for AstrBot。

每天自动抓取 GitHub Trending 热门仓库，渲染为高清排行榜图片，推送到指定的群聊或私聊。

## ✨ 功能

- **📊 排行榜图片**：深色 GitHub 风格，展示排名、仓库名、描述、语言、Star 数、今日新增 Star
- **🌐 中文翻译**：自动将英文描述翻译为中文（可开关），翻译失败静默降级保留原文
- **🔌 实时数据**：直接抓取 GitHub Trending 页面，与网站完全同步
- **🖼️ 高清渲染**：2x 缩放 1600px 宽，手绘图标零 emoji 依赖，高 DPI 屏幕清晰锐利
- **⏰ 定时推送**：每天在设定时间自动推送到所有已配置目标
- **💬 指令触发**：随时 `/trending` 手动获取
- **🎯 多目标**：支持同时推送到多个群聊和私聊
- **🔀 代理支持**：支持 HTTP/HTTPS/SOCKS5 代理，国内服务器也能正常使用翻译
- **🔑 Token 可选**：不配置也可正常使用

## 📦 安装

```bash
pip install -r requirements.txt
```

依赖：`beautifulsoup4`（HTML 解析）、`Pillow`（图片渲染）、`aiohttp`（HTTP 请求）。零额外收费 API 依赖。

## 🎮 指令参考

| 指令 | 说明 |
|------|------|
| `/trending` | 获取今日 GitHub Trending 榜单 |
| `/trending weekly` | 获取本周 GitHub Trending 榜单 |
| `/trending addhere` | 将当前群聊/私聊加入每日推送 |
| `/trending delhere` | 将当前群聊/私聊移出每日推送 |
| `/trending list` | 查看所有推送目标 |
| `/trending time 09:00` | 设置每日推送时间 |
| `/trending lang on/off` | 开启/关闭描述翻译（默认开启） |
| `/trending proxy http://x.x.x.x:port` | 设置代理 |
| `/trending token ghp_xxx` | 设置 GitHub Token（可选） |
| `/trending debug` | 诊断：逐项检查网络/解析/翻译 |
| `/trending status` | 查看当前配置和状态 |

## ⚙️ 配置说明

### 代理设置

如果服务器在国内，访问 GitHub 或 Google 翻译可能不稳定。可通过代理解决：

```bash
/trending proxy http://127.0.0.1:7890    # 设置 HTTP 代理
/trending proxy socks5://127.0.0.1:1080  # 设置 SOCKS5 代理
/trending proxy none                      # 清除代理，恢复直连
```

设置后自动清除缓存，下次请求立即生效。`/trending debug` 可验证代理是否正常工作。

### 描述翻译

默认自动将英文描述翻译为中文，使用 Google 免费翻译接口，无需 API Key。

```bash
/trending lang off   # 关闭翻译，显示英文原文
/trending lang on    # 重新开启
/trending lang       # 查看当前状态
```

> ⚠️ 如果翻译不生效（图片和文字均为英文），先跑 `/trending debug` 检查翻译测试是否通过。若失败，通常是网络问题，建议配置代理后重试。

### 故障排查

遇到问题先运行 `/trending debug`，它会逐项检查：

```
✅ GitHub 连通: HTTP 200
✅ Trending 页面: 614,880 字符
✅ HTML 解析: 14 个仓库
✅ 完整 fetch: 14 个仓库
ℹ️ 代理: http://127.0.0.1:7890
✅ 翻译器: 就绪
   翻译测试: 'Hello world test' → '你好世界测试'
   实际翻译覆盖: 14/14 条描述含中文
```

常见问题：
- 翻译覆盖 0/14 → Google API 不可达，设置代理解决
- HTML 解析 0 个仓库 → 页面结构可能变化，检查更新
- GitHub 不可达 → 网络问题，尝试设置代理

### 数据来源

直接抓取 [GitHub Trending](https://github.com/trending) 页面，一次请求拿到全部数据。与网站实时同步。

### 推送配置

- 在目标群聊/私聊发送 `/trending addhere` 即可订阅
- 默认每天 **09:00** 推送，`/trending time HH:MM` 修改

## 📸 效果预览

深色主题榜单，1600px 宽高清渲染：

```
┌─────────────────────────────────────────────────┐
│  GitHub Trending — Daily                        │
│  2026-07-10 周四                                │
│                                                 │
│  (1)  owner/repo-name                ★ 52.3k   │
│       中文描述内容…                   ▲ +2.3k   │
│       ● Python                                  │
│  ─────────────────────────────────────────────  │
│  (2)  owner/repo-name                ★ 38.1k   │
│       Description text here…         ▲ +1.8k   │
│       ● JavaScript                              │
│  ─────────────────────────────────────────────  │
│  ...                                            │
│  共 14 个项目 · 数据来自 GitHub Trending        │
│  https://github.com/trending?since=daily        │
└─────────────────────────────────────────────────┘
```

## 🛠️ 开发

```
├── main.py          # 插件入口：10 命令 + 定时调度 + 诊断 + 代理
├── fetcher.py       # 数据层：页面抓取 + HTML 解析 + 翻译集成 + 缓存
├── renderer.py      # 渲染层：2x Pillow 高清渲染（手绘图标）
├── translator.py    # 翻译模块：Google 免费接口 + 批量翻译 + 缓存
├── test_local.py    # 测试套件：fetcher、renderer、translator（64 项）
├── metadata.yaml    # 插件元数据
└── requirements.txt # 依赖清单
```

## 📄 License

MIT
