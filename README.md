# media2text

面向 Agent 工作流的个人 CLI：登录抖音、关注创作者、录制直播、同步并下载作品、转写为文本。

- **平台**：抖音（Douyin）MVP；B 站等为后续阶段
- **运行环境**：本机 Python 3.12+，数据默认落在 `./data`（已 gitignore）
- **设计文档**：[docs/superpowers/specs/2026-05-20-media2text-douyin-design.md](docs/superpowers/specs/2026-05-20-media2text-douyin-design.md)

## 功能概览

| 能力 | 说明 |
|------|------|
| 登录与会话 | Playwright 扫码/浏览器登录，会话保存在 `data/sessions/` |
| 创作者管理 | 通过主页链接解析 `sec_uid` 并登记；可选拉取昵称、头像等资料 |
| 监控开关 | `creator monitor` 开启后，统一守护进程负责直播 + 作品流水线 |
| 直播录制 | 轮询开播状态，ffmpeg 拉流录制，结束后 remux 为 `.mp4` |
| 作品同步与下载 | 打开博主主页、拦截带签名的 `aweme/post` 请求后写入 catalog，再下载视频（需有效登录态） |
| 转写 | 可选 `faster-whisper`，输出 Markdown + JSON |
| 流水线 | `sync → download → transcribe` 一键跑通 |
| Agent 友好 | 子命令稳定、`--json` 结构化输出、按创作者生成 `agent-manifest.json` |

**收录 vs 监控**：`creator add` 仅登记博主（默认不监控）；`creator monitor <id>` 开启后，`monitor watch` 才会对该博主轮询直播并跑 VOD 流水线。

## 环境要求

- macOS / Linux（开发主要在 macOS）
- [ffmpeg](https://ffmpeg.org/)（`brew install ffmpeg`）
- Python **3.12+**
- Chromium（`playwright install chromium`）

## 安装

```bash
git clone git@github.com:oychao1988/media2text.git
cd media2text

python3.12 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium

# 可选：本地语音转写
pip install -e ".[transcribe]"

# 可选：Deepgram 云端转写（官方 deepgram-sdk，REST 录完再转）
pip install -e ".[transcribe-deepgram]"
cp .env.example .env   # 填入 DEEPGRAM_API_KEY
```

复制配置并按需修改：

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

## 快速开始

```bash
# 1. 检查环境（ffmpeg、playwright、登录态、磁盘）
media2text doctor --json

# 2. 抖音登录（会打开浏览器）
media2text auth login --platform douyin
media2text auth status --json

# 3. 登记创作者（默认不开启监控；有 session 时会尝试拉取资料）
media2text creator add 'https://www.douyin.com/user/<profile>' --json

# 4. 开启监控
media2text creator monitor <creator_id> --json

# 5. 监控（直播轮询 + 作品 sync/download/transcribe）
media2text monitor watch --json          # 只跑一轮后退出（适合手动/调试）
media2text monitor watch --daemon        # 持续循环，单实例锁（见下方「守护进程」）

# 6. 手动单步（任意已登记创作者）
media2text creator sync <creator_id> --json
media2text download run --creator <creator_id> --json
media2text pipeline run --creator <creator_id> --json
```

未登录时，部分命令会使用 **fixtures** 跑通测试路径；真实拉流/同步需先完成 `auth login`。

`download run` **不带** `--creator` 时，仅处理 `monitor_enabled=1` 的创作者待下载作品。

### 守护进程（`monitor watch --daemon`）

| 命令 | 行为 |
|------|------|
| `monitor watch --json` | **单次**：检查直播 + 对已监控博主跑一轮 VOD，然后退出 |
| `monitor watch --daemon` | **持续**：按 `config.yaml` 中间隔循环（默认直播约 60s、作品约 300s） |

`--daemon` 会占用终端直至 `Ctrl+C`；若要放到系统后台：

```bash
nohup media2text monitor watch --daemon >> data/monitor-watch.log 2>&1 &
pgrep -fl "monitor watch"    # 确认在跑
```

同一时间只能有一个 daemon（锁文件 `data/.monitor-watch.lock`）。再次启动若报 `already_running`，说明已有实例在运行。

### 作品同步说明

抖音作品列表接口需要浏览器侧签名参数（`a_bogus`、`msToken` 等）。`creator sync` / 守护进程中的 VOD 会**无头打开博主主页**，拦截页面发起的 `aweme/v1/web/aweme/post/` 响应，而不是直连未签名 API。

因此：

- 需先 `auth login`，且 `doctor` 中 session 为 ok
- 每位博主首次同步可能需 **30–60 秒**（加载页面 + 滚动拉全分页）
- 若 JSON 出现 `platform_changed` 且 `aweme post status_code=5`，多为未签名请求或会话失效；重新登录后再试

## 配置

`config.yaml`（本地文件，不入库）主要字段见 `config.example.yaml`：

| 区块 | 作用 |
|------|------|
| `workspace` | 数据根目录，默认 `./data` |
| `platforms.douyin` | 下载并发、同步页数上限等 |
| `monitor.live_poll_interval_sec` | 直播状态轮询间隔（秒） |
| `monitor.vod_poll_interval_sec` | 作品 sync/download/transcribe 间隔（秒） |
| `monitor.max_creators_per_vod_tick` | 每轮 VOD 最多处理创作者数（0=不限制） |
| `monitor.profile_stale_days` | 资料过期判定天数 |
| `live` | ffmpeg 路径、临时流格式（`flv`）、`transcribe_on_complete` 直播 MP4 结束后自动转写 |
| `notify` | 监控事件提醒：系统提示音 + 飞书群机器人 webhook（见下方） |
| `transcribe` | 引擎 `whisper`（本地）、`openai`（云端）或 `deepgram`（云端 REST） |
| `transcribe.engine` | `whisper` \| `openai` \| `deepgram` |
| `transcribe.whisper.compute_type` | faster-whisper 量化（CPU 推荐 `int8`） |
| `transcribe.whisper.vad_filter` | 转写前 VAD 过滤静音（直播长视频推荐 `true`） |
| `transcribe.whisper.extract_audio` | 转写前用 ffmpeg 抽出 `{媒体}.16k.wav` sidecar |

## 转写性能（本地 CPU）

在仅有 CPU、无 CUDA/MPS 的机器上，长视频 + `medium` + 默认 float32 往往极慢。可按优先级调整：

| 手段 | 说明 |
|------|------|
| 更小模型 | `small` 或 `base` 显著缩短耗时，精度略降 |
| `compute_type: int8` | 配置默认已是 `int8`，避免 float32 隐式转换开销 |
| `extract_audio: true` | 先抽出 mono 16 kHz WAV（`*.16k.wav`），减少 faster-whisper 内部解封装；已存在且比源文件新时会跳过重复抽取 |
| `vad_filter: true` | 跳过静音段，长直播通常更快 |

### 监控提醒（`notify`）

在 `monitor watch --daemon` 运行期间，下列事件会触发**提示音**（macOS `afplay`）与**飞书文本消息**（需配置 webhook）：

| 事件 | 触发时机 |
|------|----------|
| 开播 | 检测到直播并开始 ffmpeg 录制 |
| 新作品 | VOD 同步发现 `new_count > 0` |
| 录制完成 | 直播 remux 为 `.mp4` 成功 |
| 转录完成 | 直播自动转写或 VOD 流水线转写成功 |

```yaml
notify:
  enabled: true
  sound: true
  feishu:
    webhook_url_env: NOTIFY_FEISHU_WEBHOOK_URL
```

```bash
export NOTIFY_FEISHU_WEBHOOK_URL='https://open.feishu.cn/open-apis/bot/v2/hook/xxxx'
```

可在 `notify.events` 下单独关闭某一类事件；`notify.feishu.enabled: false` 则只保留提示音。

**富文本 + 摘要 + 图片**（`notify.feishu.rich_text: true`，默认开启）：

- 转录完成：富文本里带 `.transcript.md` 摘要；未配 `media_base_url` 时另发 1–2 条 `[转写全文]` 文本消息（可直接在飞书阅读）；配了 `media_base_url` 则「转写/媒体」为可点击 HTTP 链接
- 录制完成：可选 ffmpeg 截取视频封面图
- 开播：可选拉取博主头像

图片上传需飞书**自建应用**凭证（与群内机器人同一应用），写入 `.env`：

```bash
export FEISHU_APP_ID='cli_xxx'
export FEISHU_APP_SECRET='xxx'
```

仅配置 webhook 时仍可收富文本与摘要，但不会发图片。

图片默认**单独一条** `image` 消息（比嵌在富文本里更稳定）。Webhook **不能**直接发 `.md` 附件，长文转写靠 `transcript_push`（默认开启）或 HTTP 链接二选一。

要可点击打开浏览器里的 `.transcript.md`：

```bash
# 终端 1：把 data/ 目录挂到 HTTP（会打印 LAN 地址）
media2text notify serve
```

```yaml
notify:
  feishu:
    media_base_url: http://你的局域网IP:8765   # 与 serve 输出一致
```

若仍想在飞书里贴完整本机路径：`show_local_paths: true`（手机端通常打不开）。

示例（`config.yaml`）：

```yaml
transcribe:
  whisper:
    model: small
    compute_type: int8
    vad_filter: true
    extract_audio: true
```

对比同一段素材时，可用 `time media2text transcribe run <file.mp4> --json` 观察 wall time。sidecar 文件落在媒体同目录，工作区 `data/` 已在 `.gitignore` 中。

### Deepgram 云端（`transcribe-deepgram`）

与本地 Whisper 相同，走 **录完再转写**（REST `listen.v1.media.transcribe_file`），输出格式仍为 `{媒体}.transcript.json` / `.transcript.md`。长视频会先抽 mono 16 kHz WAV（`transcribe.deepgram.extract_audio: true`）再上传，避免直传 MP4 超时。

```yaml
transcribe:
  engine: deepgram
  language: zh
  deepgram:
    api_key_env: DEEPGRAM_API_KEY
    model: nova-3
    extract_audio: true
    timeout_sec: 600
```

在 `.env` 中设置 `DEEPGRAM_API_KEY`（启动时自动加载，已 gitignore）：

```bash
media2text transcribe run path/to/video.mp4 --json
```

实时流式（WebSocket / Flux）未接入 CLI，仅用于实验脚本 `scripts/test_deepgram_sdk*.py`。

Deepgram 后处理（`smart_format: false` 时）：去掉中文词间空格；`text` 按 utterance 换行（与 `segments` 一一对应），段内遇 `。！？；…` 再拆行。JSON 里 `text` 为含 `\n` 的多行字符串。

## 工作区目录

```
data/
  media2text.db              # SQLite（创作者、作品、直播会话）
  sessions/douyin.json       # Playwright 登录态（0600，勿提交）
  .monitor-watch.lock        # 统一监控守护进程锁
  creators/{sec_uid}/
    agent-manifest.json      # Agent 索引（路径与状态）
    videos/{aweme_id}.mp4
    live/{timestamp}.mp4
```

## 命令参考

所有子命令均支持 `--json`，便于 Cursor / Claude 等 Agent 解析。

| 命令 | 说明 |
|------|------|
| `media2text doctor [--json]` | 检查 ffmpeg、playwright、session、磁盘 |
| `media2text auth login --platform douyin` | 交互登录 |
| `media2text auth status [--json]` | 会话是否存在 |
| `media2text creator add <url> [--json]` | 登记创作者（默认不监控） |
| `media2text creator list [--json]` | 列出已登记创作者 |
| `media2text creator show <id> [--json]` | 资料、监控状态、作品计数 |
| `media2text creator refresh <id> [--json]` | 更新博主资料 |
| `media2text creator monitor <id> [--off] [--json]` | 开启/关闭监控 |
| `media2text creator sync <creator_id> [--json]` | 同步作品 catalog |
| `media2text creator remove <creator_id> [--delete-media] [--json]` | 移除创作者；可选删除 `data/creators/{sec_uid}/` |
| `media2text monitor watch [--daemon] [--creator <id>] [--json]` | 统一监控（直播 + VOD） |
| `media2text download run [--creator <id>] [--limit N] [--json]` | 下载待处理作品（可限制条数） |
| `media2text transcribe run <path> [--creator <id>] [--json]` | 转写文件或目录 |
| `media2text pipeline run --creator <id> [--json]` | sync + download + transcribe |
| `media2text version` | 打印版本号 |

### 退出码

| 码 | 含义 |
|----|------|
| `0` | 成功 |
| `1` | 一般错误（如 doctor 未通过、守护进程已运行） |
| `2` | 需要登录（`auth_required`） |
| `3` | 解析/页面结构变化 |
| `4` | 部分失败（如下载/转写未完成） |

## 开发

```bash
source .venv/bin/activate

# 测试（默认不含真实网络）
pytest tests/ -v

# 需要真实抖音网络时
pytest tests/ -v -m live

# 静态检查
ruff check src tests
pyright
```

实现计划与分步提交说明见 [docs/superpowers/plans/2026-05-20-media2text-douyin.md](docs/superpowers/plans/2026-05-20-media2text-douyin.md)。

## 仓库

- 远程：`git@github.com:oychao1988/media2text.git`
- 勿将 `data/`、`config.yaml`、`.venv/` 提交到 Git（已在 `.gitignore`）

## 状态说明

当前为 **0.1.0 MVP**：核心 CLI 与离线 fixtures 已就绪；在有效抖音会话下可进行统一监控与 VOD 流水线（作品 sync 经 Playwright 拦截签名请求）。请关注 `doctor` 与 JSON 中的 `auth_required`；`platform_changed` 表示解析失败或接口返回非 0 业务码（含页面结构变化与未签名/被拒的 API 响应）。
