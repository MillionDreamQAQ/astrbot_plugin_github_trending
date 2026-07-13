# astrbot_plugin_github_trending

🔥 GitHub Trending 榜单推送插件 for AstrBot。

每天自动抓取 GitHub Trending 热门仓库，渲染为高清排行榜图片，推送到指定的群聊或私聊。支持独立订阅系统：每个群可设置独立的推送时间和语言/社区过滤，同一群可同时订阅多个榜单。

## ✨ 功能

- **📊 排行榜图片**：深色 GitHub 风格，展示排名、仓库名、描述、语言、Star 数、今日新增 Star
- **📬 独立订阅**：每个群/私聊独立设置推送时间和语言/社区，同一群支持多个榜单订阅
- **🌐 中文翻译**：自动将英文描述翻译为中文（可开关），翻译失败静默降级保留原文
- **🔌 实时数据**：直接抓取 GitHub Trending 页面，与网站完全同步
- **🖼️ 高清渲染**：2x 缩放 1600px 宽，手绘图标零 emoji 依赖，高 DPI 屏幕清晰锐利
- **⏰ 定时推送**：每分钟轮询，支持任意数量的不同推送时间
- **💬 指令触发**：随时 `/trending` 手动获取
- **🔀 代理支持**：支持 HTTP/HTTPS/SOCKS5 代理，国内服务器也能正常使用翻译

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
| `/trending addhere [参数...]` | 创建订阅（参数顺序任意） |
| `/trending delhere [id]` | 删除订阅（无 id 则删全部） |
| `/trending list` | 查看所有订阅 |
| `/trending sub <id> <操作>` | 管理订阅（enable/disable/time/language/community） |
| `/trending time 09:00` | 设置每日推送时间 |
| `/trending lang on/off` | 开启/关闭描述翻译（默认开启） |
| `/trending proxy http://x.x.x.x:port` | 设置代理 |
| `/trending language <lang>` | 按编程语言过滤（如 python、rust） |
| `/trending community <code>` | 按社区过滤（如 zh、ja） |
| `/trending token ghp_xxx` | 设置 GitHub Token（可选） |
| `/trending help` | 显示命令帮助 |
| `/trending debug` | 诊断：逐项检查网络/解析/翻译 |
| `/trending status` | 查看当前配置和状态 |

## ⚙️ 配置说明

### 订阅管理

每个群/私聊可以创建**多个订阅**，每个订阅独立设置推送时间和过滤条件。

参数规则（`addhere` 后的参数顺序任意）：

| 参数特征 | 识别为 |
|----------|--------|
| 含 `:` 的（如 `09:00`） | 推送时间 |
| 2 字母如 `zh` `ja` `ko` | 社区代码 |
| 其他如 `python` `rust` | 编程语言 |

```bash
# 创建订阅（使用默认设置）
/trending addhere

# 指定各维度（顺序任意）
/trending addhere 18:00 zh
/trending addhere python zh 18:00
/trending addhere 09:00 python zh

# 查看所有订阅
/trending list

# 修改某个订阅
/trending sub abc123 time 09:00        # 改时间
/trending sub abc123 community zh       # 改社区
/trending sub abc123 language python    # 改语言
/trending sub abc123 disable            # 暂停
/trending sub abc123 enable             # 恢复

# 删除某个订阅
/trending delhere abc123

# 删除当前会话的全部订阅
/trending delhere
```

同一个群可以同时拥有"全球榜单 9:00"和"中文社区 18:00"两个订阅，互不干扰。

### 语言过滤

支持两层过滤，可以组合使用：

```bash
# 编程语言过滤
/trending language python    # 只看 Python 项目
/trending language rust      # 只看 Rust 项目
/trending language all        # 恢复全语言

# 社区（口语）过滤
/trending community zh       # 中文社区
/trending community ja       # 日文社区
/trending community all       # 不限社区
```

两个过滤可以同时生效，例如 `/trending language python` + `/trending community zh` = 中文社区的 Python 热门项目。

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
├── main.py          # 插件入口：13 命令 + 独立订阅调度 + 诊断 + 代理
├── fetcher.py       # 数据层：页面抓取 + HTML 解析 + 翻译集成 + 缓存
├── renderer.py      # 渲染层：2x Pillow 高清渲染（手绘图标）
├── translator.py    # 翻译模块：Google 免费接口 + 批量翻译 + 缓存
├── test_local.py    # 测试套件：fetcher、renderer、translator（64 项）
├── metadata.yaml    # 插件元数据
└── requirements.txt # 依赖清单
```

## 📄 License

MIT
