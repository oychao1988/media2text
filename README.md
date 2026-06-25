# media2text

面向 Agent 工作流的个人 CLI：登录抖音、关注创作者、录制直播、同步并下载作品、转写为文本。

- **平台**：抖音（Douyin）+ B 站（`--platform bilibili`：直播 / 投稿 / 动态）
- **运行环境**：本机 Python 3.12+，数据默认落在 `./data`（已 gitignore）
- **设计文档**：[抖音](docs/superpowers/specs/2026-05-20-media2text-douyin-design.md) · [B 站](docs/superpowers/specs/2026-05-20-media2text-bilibili-design.md)

**声明**：本工具为**个人研究档案工具**，用于本地录制、转写与检索复盘，**不构成投资咨询**，不提供荐股、跟单或买卖建议。使用 `archive search` 等检索能力前需执行 `media2text compliance accept` 确认免责声明。

## 功能概览

| 能力 | 说明 |
|------|------|
| 登录与会话 | Playwright 扫码/浏览器登录，会话保存在 `data/sessions/` |
| 创作者管理 | 通过主页链接解析 `sec_uid` 并登记；可选拉取昵称、头像等资料 |
| 监控开关 | `creator monitor` 开启后，统一守护进程负责直播 + 作品流水线 |
| 直播录制 | 轮询开播状态，ffmpeg 拉流；**新用户推荐** `streaming` + `live.media.format=hls` + `segment_pipeline.enabled=true`（HLS 分段 + 段级上云）；legacy 为 FLV/MP4 整文件路径 |
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

### B 站快速开始

规格：[docs/superpowers/specs/2026-05-20-media2text-bilibili-design.md](docs/superpowers/specs/2026-05-20-media2text-bilibili-design.md)

```bash
media2text auth login --platform bilibili
media2text creator add 'https://space.bilibili.com/<mid>' --platform bilibili --json
media2text creator monitor <creator_id> --json

# 守护进程：直播 + 投稿（archive）+ 动态 三档轮询（见 config platforms.bilibili）
media2text monitor watch --daemon

# 手动单轮
media2text creator sync <creator_id> --json           # 仅投稿 catalog
media2text creator sync-dynamics <creator_id> --json  # 仅动态 feed（文字+图片）
media2text pipeline run --creator <creator_id> --json
media2text archive index --json                       # 含 dynamics/*/content.md FTS
```

`doctor --json` 在已登记 B 站创作者时会额外检查 `sessions/bilibili.json`。通知事件：`new_archive`（投稿）、`new_dynamic`（动态）；抖音仍用 `new_aweme`。

未登录时，部分命令会使用 **fixtures** 跑通测试路径；真实拉流/同步需先完成 `auth login`。

`download run` **不带** `--creator` 时，仅处理 `monitor_enabled=1` 的创作者待下载作品。

### 守护进程（`monitor watch --daemon`）

| 命令 | 行为 |
|------|------|
| `monitor watch --json` | **单次**：检查直播 + 对已监控博主跑一轮 VOD，然后退出 |
| `monitor watch --daemon` | **持续**：`LiveTick` 默认 `live.live_poll_interval_sec`（10s）；`PostProcessPool` 异步后处理；抖音作品约 300s；B 站投稿/动态见 `platforms.bilibili` |

`--daemon` 会占用终端直至 `Ctrl+C`；若要放到系统后台：

```bash
nohup bin/monitor-watch-daemon.sh >> data/monitor-watch.log 2>&1 &
pgrep -fl "monitor watch"    # 确认在跑
```

脚本会设置 `PLAYWRIGHT_BROWSERS_PATH`（默认 `~/Library/Caches/ms-playwright`）并清理已死进程留下的锁；抖音直播 reflow 依赖该路径下的 Chromium。

收到 SIGTERM/SIGINT（含 Desktop「停止终端守护」、`takeover` 前的 stop）时会先 `scheduler.stop()` 再退出，避免 ffmpeg / 队列任务孤儿化。

**macOS 开机自启（LaunchAgent 示例）**：在项目根目录创建 `~/Library/LaunchAgents/com.media2text.monitor.plist`（路径按本机修改）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.media2text.monitor</string>
  <key>WorkingDirectory</key><string>/Users/YOU/Documents/Projects/media2text</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/Documents/Projects/media2text/bin/monitor-watch-daemon.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/YOU/Documents/Projects/media2text/data/monitor-watch.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/Documents/Projects/media2text/data/monitor-watch.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.media2text.monitor.plist
launchctl list | grep media2text
```

Desktop 与 CLI **同一时刻仅一个 monitor owner**（锁文件互斥）。`desktop.auto_start_monitor=true` 时：已有 CLI 则 Desktop **沿用** CLI；无 CLI 则 Desktop 自动启内嵌监控。切换见 DaemonCard「改用 Desktop / 改用终端」或 `POST /api/runtime/takeover|handoff`。

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
| `monitor.live_poll_interval_sec` | 直播轮询回退间隔（秒）；优先用 `live.live_poll_interval_sec` |
| `live.live_poll_interval_sec` | LiveTick 直播检测间隔（默认 10；回退 `monitor.live_poll_interval_sec`） |
| `live.offline_confirm_polls` | API 连续 offline 次数后才停录（默认 3） |
| `live.post_process_poll_interval_sec` | 守护进程内 drain 后处理队列间隔 |
| `monitor.vod_poll_interval_sec` | 作品 sync/download/transcribe 间隔（秒） |
| `monitor.max_creators_per_vod_tick` | 每轮 VOD 最多处理创作者数（0=不限制） |
| `monitor.profile_stale_days` | 资料过期判定天数 |
| `live.pipeline_mode` | `streaming`（并行录制 + Deepgram WS，抖音/B 站直播；example 推荐）或 `legacy`（代码默认：remux MP4 + 录后转写） |
| `live.media.format` | `flv`（单文件）或 `hls`（`master.m3u8` + 分段；需 `pipeline_mode=streaming`） |
| `live.media.segment_duration_sec` | HLS 段时长（秒），默认 600 |
| `live.segment_pipeline` | 段闭合检测、上传、删本地；`enabled` / `max_parallel` / `upload.delete_local_after_upload` |
| `live.streaming_stt.enabled` | `false` 时仅录制、不启 WS（即使 `pipeline_mode=streaming`）；session 快照为 `legacy` |
| `live.remux_on_complete` | streaming 默认 `false`；`format=flv` 时可选额外 remux MP4；HLS 不走整文件 remux |
| `live` | ffmpeg、重连/离线确认；streaming 需 `DEEPGRAM_API_KEY` + `.[transcribe-deepgram]` + 对应平台登录态；`transcribe_on_complete` 仅 legacy FLV |
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

实时流式（`live.pipeline_mode: streaming`）在录制期间通过 **Deepgram `listen.v1` WebSocket** 出字，按流式用量计费（与 REST 录后转写分开计费）。需 `pip install -e ".[transcribe-deepgram]"` 与 `DEEPGRAM_API_KEY`；可选 `notify.events.transcribe_partial: true` 推送 partial 摘要（默认关）。验收指标见 `media2text live stats --json` 的 `streaming.metrics`：

| 指标 | 含义 |
|------|------|
| **S1** `s1_finalize_stt_ms` | 下播 → transcript 封存（`streaming_stt` stage 耗时） |
| **S2** `s2_offline_to_complete_ms` | 下播确认 → 会话 `ended_at`（finalize 完成，无 remux） |
| **S3** `s3_offline_to_summarize_ms` | 下播确认 → `summarize` stage 完成（post_process 摘要） |
| 首条 final | 开播 → 首条 final 字幕（`first_final_latency_ms`） |

S2 口径为 DB 中 `offline_pending` 至 `live_sessions.ended_at`，与 `recording_completed` 通知时刻可能差数秒。S3 口径为 `offline_pending` 至 `summarize` completed 的 `ended_at`。`targets_ms.s3_offline_to_summarize_p95` 默认 180s，待 dogfood 校准。

### streaming 延迟自检

对比近 N 天 streaming 场次的 P95 与 `streaming.targets_ms`（S1/S2/S3/首条 final，见上表）：

```bash
media2text live stats --days 7 --json --check-targets
```

- 退出码 **0**：有样本且全部达标，或窗口内无可用样本（`target_check.insufficient_data: true`）
- 退出码 **1**：至少一项 P95 超标；JSON 含 `target_check.violations` 与 `over_by_ms`
- 查看某博主最近一场直播的 `pipeline_mode` / `transcribe_status`：`media2text creator show <id> --json` → `latest_live_session`

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
| `media2text creator refresh <id> [--json]` | 更新博主资料（抖音 / B 站，按 `platform` 自动选适配器） |
| `media2text creator monitor <id> [--off] [--json]` | 开启/关闭监控 |
| `media2text creator sync <creator_id> [--json]` | 同步作品 catalog |
| `media2text creator remove <creator_id> [--delete-media] [--json]` | 移除创作者；可选删除 `data/creators/{sec_uid}/` |
| `media2text monitor watch [--daemon] [--creator <id>] [--json]` | 统一监控（直播 + VOD） |
| `media2text post-process run [--limit N] [--json]` | 手动消化直播后处理队列 |
| `media2text post-process retry <job_id> --json` | 将失败的后处理任务重置为 pending |
| `media2text download run [--creator <id>] [--limit N] [--json]` | 下载待处理作品（可限制条数） |
| `media2text transcribe run <path> [--creator <id>] [--json]` | 转写文件或目录 |
| `media2text summarize run <path> [--creator <id>] [--json]` | LLM 摘要（需 `summarize.enabled` + `NVIDIA_API_KEY`） |
| `media2text summarize backfill [--creator <id>] [--limit N] [--json]` | 缺 summary 的历史转写批量补跑 |
| `media2text summarize merge --sessions <id1>,<id2> [--json]` | 多段直播合并摘要 |
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

## Desktop（m2t-desktop）

macOS 优先的 Tauri 2 桌面壳：三栏 UI + Python API sidecar（`:8765`）+ Node Agent sidecar。规格见 [m2t-desktop-design](docs/superpowers/specs/2026-06-04-m2t-desktop-design.md)。

### 环境

除 CLI 通用依赖外，桌面端还需要：

| 依赖 | 用途 |
|------|------|
| [ffmpeg](https://ffmpeg.org/) | 直播录制 / remux（与 CLI 相同） |
| Chromium（`playwright install chromium`） | 平台登录、`creator sync` |
| Node 20+、pnpm 9 | 前端 workspace 与 Agent sidecar |
| Rust / Xcode CLT | Tauri 构建（`tauri dev` / `tauri build`） |
| 可选 `pip install -e ".[transcribe-deepgram]"` + `.env` 的 `DEEPGRAM_API_KEY` | streaming 模式实时转写 |

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
playwright install chromium

# 根目录：安装 JS workspace
pnpm install
```

### 开发运行

**仅调试 API（无 Tauri 窗口）：**

```bash
media2text serve --port 8765
curl -s http://127.0.0.1:8765/api/health | jq .
media2text doctor --json
```

**完整桌面应用（Tauri 自动 spawn Python serve + Agent sidecar）：**

```bash
pnpm --filter m2t-desktop tauri dev
# 或仓库根目录
pnpm dev:desktop
```

数据目录与 CLI 共用 `./data`（`config.yaml`、会话、DB）。验收清单：[2026-06-04-m2t-desktop-acceptance](docs/superpowers/verification/2026-06-04-m2t-desktop-acceptance.md)。

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
