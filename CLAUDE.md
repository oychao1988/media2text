# media2text — Agent 指南

个人 CLI：抖音创作者直播录制、作品同步下载、语音转文字。面向 Cursor / Claude 等 Agent 调用时优先读本文 + `README.md`。

- 设计规格：[docs/superpowers/specs/2026-05-20-media2text-douyin-design.md](docs/superpowers/specs/2026-05-20-media2text-douyin-design.md)
- 用户文档：[README.md](README.md)

## 项目要点

| 项 | 说明 |
|----|------|
| 平台 | 抖音 MVP（`--platform douyin`） |
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

### 2. 长期监控（直播 + 作品）

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
| `--daemon` | 循环：直播轮询（默认 ~60s）+ VOD（默认 ~300s） |

停止：`pkill -f "media2text monitor watch"` 或 `kill $(cat data/.monitor-watch.lock)`。

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

直播结束自动转写：配置 `live.transcribe_on_complete: true` 且已安装对应转写 extra。

监控提醒（`notify.enabled: true`）：开播 / 新作品 / 录制完成 / 转录完成 → 系统提示音 + 飞书 webhook（`NOTIFY_FEISHU_WEBHOOK_URL`）。

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
| `creator remove <id> [--delete-media] --json` | 移除博主 |
| `monitor watch [--daemon] [--creator <id>] --json` | 直播 + VOD 监控 |
| `download run [--creator <id>] [--limit N] --json` | 下载视频 |
| `transcribe run <path> --json` | 转写 |
| `pipeline run --creator <id> --json` | 作品一条龙 |

## 工作区与 Agent 索引

```
data/
  media2text.db
  sessions/douyin.json          # 登录态，勿提交
  .monitor-watch.lock           # 守护进程锁
  creators/{sec_uid}/
    agent-manifest.json         # 读路径/状态优先用这个
    videos/{aweme_id}.mp4
    live/{timestamp}.mp4
    live/{timestamp}.transcript.md
    live/{timestamp}.transcript.json
```

处理某博主媒体时：先读 `data/creators/{sec_uid}/agent-manifest.json`，再按路径读转写文件。

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
