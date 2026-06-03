# media2text — Agent 指南

个人 CLI：抖音 / B 站创作者直播录制、作品与动态同步、语音转文字。面向 Cursor / Claude 等 Agent 调用时优先读本文 + `README.md`。

- 抖音规格：[docs/superpowers/specs/2026-05-20-media2text-douyin-design.md](docs/superpowers/specs/2026-05-20-media2text-douyin-design.md)
- B 站规格：[docs/superpowers/specs/2026-05-20-media2text-bilibili-design.md](docs/superpowers/specs/2026-05-20-media2text-bilibili-design.md)
- 用户文档：[README.md](README.md)

## 项目要点

| 项 | 说明 |
|----|------|
| 平台 | 抖音（`douyin`）+ B 站（`bilibili`：直播 / 投稿 / 动态） |
| 数据目录 | `./data`（gitignore，含 DB、会话、媒体） |
| 配置 | `config.yaml`、` .env`（本地，勿提交） |
| CLI 入口 | `media2text`（`pip install -e ".[dev]"` 后） |
| JSON 输出 | 子命令加 `--json`，便于解析 |

**收录 vs 监控**：`creator add` 只登记；`creator monitor <id>` 开启后，`monitor watch` 才会录直播并跑作品流水线。

## 环境（改代码 / 跑 CLI 前）

```bash
source .venv/bin/activate   # 项目根目录
media2text doctor --json    # ffmpeg、playwright、session、磁盘
```

依赖：Python 3.12+、ffmpeg、Chromium（`playwright install chromium`）。

可选 extra：`pip install -e ".[transcribe]"` / `".[transcribe-deepgram]"`。

## 常用流程

### 1. 首次使用

```bash
cp config.example.yaml config.yaml
cp .env.example .env          # 若用 Deepgram / OpenAI 转写

media2text auth login --platform douyin
media2text auth status --json

media2text creator add 'https://www.douyin.com/user/<sec_uid或主页链接>' --json
media2text creator monitor <creator_id> --json
```

**B 站**（需 `auth login --platform bilibili`）：

```bash
media2text creator add 'https://space.bilibili.com/<mid>' --platform bilibili --json
media2text creator monitor <creator_id> --json
media2text creator sync-dynamics <creator_id> --json   # 仅动态一轮
```

### 2. 长期监控（直播 + 作品 / B 站动态）

```bash
# 单次（调试）
media2text monitor watch --json

# 持续守护（推荐后台）
nohup media2text monitor watch --daemon >> data/monitor-watch.log 2>&1 &
pgrep -fl "monitor watch"
cat data/.monitor-watch.lock   # 单实例 PID
```

| 模式 | 行为 |
|------|------|
| 无 `--daemon` | 跑一轮后退出 |
| `--daemon` | **三线程**：`LiveTick`（抖音/B 站 live poll + 非阻塞 post-process claim/submit，默认 `live.live_poll_interval_sec` 10s，回退 `monitor.live_poll_interval_sec`）；`SlowTick`（VOD / B 站 archive / dynamic，各自 poll 间隔）；`PostProcessPool`（worker 每 job 独立 `open_db`）。主线程持锁 idle |

停止：`pkill -f "media2text monitor watch"` 或 `kill $(cat data/.monitor-watch.lock)`。

直播收尾：`finalize` 仅 remux + 入队 `post_process_jobs`；转写/摘要/云盘在 drain 中异步执行。手动清队列：`media2text post-process run [--limit N] --json`。通知时序：首次 API offline → `live_ended`；满 `live.offline_confirm_sec`（默认 45s）仍 offline → remux → `recording_completed`；`transcribe_completed` / `summarize_completed` 在 worker 完成后。`min_recording_sec_before_offline_end`（默认 45s）忽略开播后短暂 offline；ffmpeg 异常退出可分段重连（`max_reconnect_attempts`）。

### 3. 手动作品流水线（单博主）

```bash
media2text creator sync <creator_id> --json      # 同步 catalog（较慢，见下）
media2text download run --creator <creator_id> --json
media2text pipeline run --creator <creator_id> --json   # sync + download + transcribe 一步
```

`download run` 不带 `--creator` 时，仅处理 `monitor_enabled=1` 的待下载作品。

### 4. 转写

```bash
# 单文件
media2text transcribe run data/creators/<sec_uid>/live/xxx.mp4 --json

# 引擎在 config.yaml：transcribe.engine = whisper | openai | deepgram
```

直播结束自动转写：配置 `live.transcribe_on_complete: true` 且已安装对应转写 extra；由 `monitor watch --daemon` 的 `PostProcessPool` 或 `post-process run` 执行，不在 finalize 内阻塞。

### 4a. LLM 摘要（`summarize`，与转写引擎独立）

依赖 `pip install -e ".[transcribe-cloud]"` 与 `.env` 的 `NVIDIA_API_KEY`（或改 `summarize.llm` 指向其它 OpenAI 兼容端点）。

```bash
# config.yaml: summarize.enabled: true
media2text summarize run data/creators/<sec_uid>/live/xxx.mp4 --json
media2text summarize run --creator <creator_id> --json   # 含 suggested_groups（分段直播合并建议）
media2text summarize backfill [--creator <id>] [--limit N] --json  # 缺 summary 的历史转写批量补跑
media2text summarize merge --sessions <id1>,<id2> --json
```

Sidecar：`{basename}.summary.md` + 元数据 `{basename}.summary.json`；合并直播：`live/YYYYMMDD_merged.summary.md`。`agent-manifest.json` 含 `summary_path`、`live_groups`。

### 4b. 个人阿里云盘（实验，非 CLI 子命令）

个人版 Web API（与 [foyoux/aligo](https://github.com/foyoux/aligo) 同路径）。Token：`data/sessions/aliyundrive.token.json`。

```bash
# 登录（推荐 QR；或 .env 的 ALIYUN_DRIVE_REFRESH_TOKEN + --mode token）
python scripts/aliyundrive_login.py --mode qr

# API 冒烟（列表/容量/上传/下载/删除）
python scripts/aliyundrive_api_test.py
```

账户剩余空间用 `getUserCapacityInfo`，勿用 `drive/get` 单盘 `used_size`。

**直播云备份（阶段 B，`aliyundrive.enabled: true`）**

- 登录：`media2text auth login --platform aliyundrive`（或 `python scripts/aliyundrive_login.py --mode qr`）
- 收尾顺序：remux → 录制完成通知 →（可选）转写 → 云备份 MP4 + sidecar → 默认删本地
- 云路径：`{root_folder}/{platform}/{nickname}/live/{timestamp}.mp4`（nickname 来自 profile `display_name`，上传前强制 sync）
- 空间不足：`on_insufficient_space: rolling_cleanup` 按 `cloud_uploads.uploaded_at` 删最旧已完整备份；飞书 `upload_cleanup` 列举文件名
- 关键配置：`upload_transcripts`、`delete_local_after_upload`（默认 true）、`min_free_bytes`、`notify.events.upload_*`

监控提醒（`notify.enabled: true`）：开播 / 新作品 / 录制完成 / 转录完成 / 云备份 → 系统提示音 + 飞书 webhook（`NOTIFY_FEISHU_WEBHOOK_URL`）。

### 5. 查看已登记博主

```bash
media2text creator list --json
media2text creator show <creator_id> --json
```

## 命令速查

| 命令 | 用途 |
|------|------|
| `doctor --json` | 环境自检 |
| `auth login` / `auth status --json` | 登录 / 会话 |
| `creator add <url> --json` | 登记博主 |
| `creator monitor <id> [--off] --json` | 开/关监控 |
| `creator sync <id> --json` | 同步作品列表 |
| `creator sync-dynamics <id> --json` | B 站：仅动态一轮 |
| `creator remove <id> [--delete-media] --json` | 移除博主 |
| `monitor watch [--daemon] [--creator <id>] --json` | 直播 + VOD/archive + 动态 |
| `post-process run [--limit N] --json` | 消化积压的直播后处理任务 |
| `post-process retry <job_id> --json` | 将 `failed` 后处理任务重置为 `pending` |
| `live status [--creator <id>] --json` | 当前录制、后处理队列与 daemon 锁 |
| `live timeline <session_id> --json` | 单场 pipeline events 时间线 |
| `live stats [--days N] --json` | 各 stage 耗时 P50/P95 聚合 |

`live.scan_concurrency`（默认 4）并行 poll 无 active session 的博主；`post_process_max_parallel: 0` 为自适应 worker 数。
| `download run [--creator <id>] [--limit N] --json` | 下载视频 |
| `transcribe run <path> --json` | 转写 |
| `summarize run <path> [--creator <id>] --json` | 转写摘要（含 `suggested_groups`） |
| `summarize backfill [--creator <id>] [--limit N] --json` | 工作区内缺 `.summary.md` 的转写批量补摘要 |
| `summarize merge --sessions <ids> --json` | 多段直播合并摘要 |
| `pipeline run --creator <id> --json` | 作品一条龙 |

## 工作区与 Agent 索引

```
data/
  media2text.db
  sessions/douyin.json          # 抖音登录态
  sessions/bilibili.json        # B 站登录态
  .monitor-watch.lock           # 守护进程锁
  creators/{sec_uid}/
    agent-manifest.json         # 读路径/状态优先用这个
    videos/{aweme_id}.mp4
    live/{timestamp}.mp4
    live/{timestamp}.transcript.md
    live/{timestamp}.transcript.json
    dynamics/{id}/content.md    # B 站动态正文（archive index 可检索）
```

处理某博主媒体时：先读 `data/creators/{sec_uid}/agent-manifest.json`（B 站含 `archives` / `dynamics` 分块），再按路径读转写或 `content.md`。

**B 站监控**：`monitor watch` 对 `platform=bilibili` 维护 live / archive / dynamic 三档时钟（`platforms.bilibili.*_poll_interval_sec`）。通知：`new_archive`、`new_dynamic`（抖音 `new_aweme`）。

## 作品 sync 机制（排错必读）

- **不能**对 `aweme/post` 做未签名 HTTP 直连；会得 `status_code=5`、`platform_changed: true`。
- 实现：无头打开博主主页，**拦截**页面发起的带签名 `aweme/v1/web/aweme/post/` XHR（见 `playwright_client.py`）。
- 每位博主首次 sync 约 **30–60s**；守护进程 VOD 轮询同理。
- `auth_required: true` → 需 `auth login`。
- `already_running` → 已有 `monitor watch --daemon`，勿重复启动。

## JSON 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 一般错误 / 守护进程已运行 |
| 2 | 需要登录 |
| 3 | 解析或平台响应异常（含 `platform_changed`） |
| 4 | 部分失败（下载/转写） |

## 开发

```bash
pytest tests/ -v              # 默认无真实网络
pytest tests/ -v -m live       # 需抖音网络
ruff check src tests
pyright
```

抖音适配器：`src/media2text/core/platform/douyin/`（`adapter.py`、`playwright_client.py`、`catalog.py`、`live.py`）。

## Agent 操作约束

- 不要提交 `data/`、`config.yaml`、`.env`、`.venv/`、`.playwright-mcp/`。
- 改 CLI 行为时同步考虑 `--json` 字段与 `agent-manifest.json` 刷新。
- 未要求时不要 force-push `main`；PR 用 `gh`，合并前看 CI。
- 用户未明确要求时，不要擅自 `git commit` / 启动长期 daemon。

## 配置摘录（`config.yaml`）

```yaml
workspace: ./data
notify:
  enabled: false
  sound: true
  feishu:
    webhook_url_env: NOTIFY_FEISHU_WEBHOOK_URL
monitor:
  live_poll_interval_sec: 60
  vod_poll_interval_sec: 300
live:
  transcribe_on_complete: false   # 直播 MP4 完成后自动转写
transcribe:
  engine: whisper                 # whisper | openai | deepgram
  whisper:
    model: small                  # CPU 长视频建议 small + int8
    compute_type: int8
    vad_filter: true
    extract_audio: true
```

完整字段见 [config.example.yaml](config.example.yaml)。
