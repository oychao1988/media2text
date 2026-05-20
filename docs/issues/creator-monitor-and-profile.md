# 创作者收录与统一监控

## 背景

当前 `creator add` 仅解析 `sec_uid` 与 `profile_url` 入库，`display_name` 等字段几乎为空，`creator list` 只能看到链接，难以管理。

监控方面仅有 `watch_live` 控制直播守护进程；作品同步/下载/转写需手动按 `creator_id` 执行，且 `download run` 无 `--creator` 时会处理所有已收录博主，与「收录 ≠ 监控」的预期不符。

**产品约定（已确认）：**

1. **收录**：`creator add` 登记博主并尽量拉取资料，**默认不开启监控**。
2. **监控**：单一开关；开启后对同一博主自动：直播录制 + 新作品 sync/download + 转写（在 transcribe 可用时）。

## 验收标准

### P1 — 资料与收录

- [ ] `creators` 表扩展（或等价迁移）：`unique_id`、`avatar_url`、`profile_synced_at`（可选 `signature`、`follower_count`）；新增 `monitor_enabled INTEGER NOT NULL DEFAULT 0`。
- [ ] 实现 `parse_user_profile`（或复用 profile API / `RENDER_DATA`），从 Douyin adapter 返回结构化资料。
- [ ] `creator add <url>`：**默认 `monitor_enabled=0`**；有 session 时尝试拉 profile 写入 `display_name` 等；失败不阻塞收录。
- [ ] 新增 `creator refresh <id>`：更新资料并刷新 `profile_synced_at`。
- [ ] `creator list --json` 输出：`display_name`、`unique_id`、`monitor_enabled`、`profile_stale`（无资料或过期时 true）、`profile_url`。
- [ ] 新增 `creator show <id> --json`：资料 + `monitor_enabled` + 作品/待下载计数（基于现有 awemes 表）。

### P2 — 监控开关与管理

- [ ] 新增 `creator monitor <id>` / `creator monitor <id> --off`（或 `creator update --monitor/--no-monitor`），切换 `monitor_enabled`。
- [ ] DB 迁移：将既有 `watch_live=1` 的行一次性设为 `monitor_enabled=1`（兼容旧数据）；之后以 `monitor_enabled` 为唯一真相源（`watch_live` 列可在迁移后弃用/不再写入）。
- [ ] **移除** `creator add` 的 `--watch-live` / `--no-watch-live` 选项；收录与监控完全分离。
- [ ] `download run` **无 `--creator` 时**仅处理 `monitor_enabled=1` 的创作者待下载项（或文档+CLI 强制要求 `--creator`；二选一须在 PR 说明理由）。

### P3 — 统一守护进程

- [ ] 新增 **`monitor watch`** 子命令（`--daemon`、`--creator <id>`、`--json`）；**移除**对外 `live watch`（无别名，README/CLI help 一并更新）。  
  - 直播：对 `monitor_enabled=1` 轮询开播并录制（复用现有 `LiveWatcher`）。  
  - 作品：按配置间隔对每个监控中创作者执行 `sync → download_pending → transcribe`（复用 `run_pipeline` / 现有函数，避免重复实现）。
- [ ] `config.yaml` 增加 `monitor.live_poll_interval_sec`、`monitor.vod_poll_interval_sec`（及可选 `max_creators_per_vod_tick`）。
- [ ] 守护进程 workspace 锁（可沿用 `.live-watch.lock` 或改为 `.monitor-watch.lock`，PR 说明）；JSON 输出含 per-creator 错误，不静默吞掉 `auth_required`。
- [ ] README 更新：收录 vs 监控、`creator add` 默认不监控、`monitor watch` 用法。

### 测试

- [ ] 单元测试：profile 解析（fixtures）、`monitor_enabled` repo 方法、迁移逻辑（如有）。
- [ ] 现有 `pytest tests/ -v` 全绿；新增测试覆盖 P1–P2 核心路径（daemon 可用 mock/单轮 `run_once` 测）。

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/ -v

# P1 手工（fixtures 路径）
media2text creator add 'https://www.douyin.com/user/<profile>' --json
media2text creator list --json
media2text creator refresh <creator_id> --json
media2text creator show <creator_id> --json

# P2
media2text creator monitor <creator_id> --json
media2text creator monitor <creator_id> --off --json

# P3（单轮或短时 daemon，需登录时见 auth_required）
media2text monitor watch --json
# media2text monitor watch --daemon  # 本地验证时 Ctrl+C
```

## 非目标范围

- Web UI / TUI 管理界面。
- 按创作者自定义 poll 间隔、标签分组、批量 import CSV。
- 关监控时强制 kill 进行中的 ffmpeg（可选后续；本单默认录完当前场次或文档写明行为）。
- B 站等其他平台。
- 未安装 `[transcribe]` 时仍应 sync/download；转写跳过并在 JSON 标注，不视为验收失败。

## 实现提示（给修单 Agent）

- 复用：`src/media2text/core/platform/douyin/parse.py`、`adapter.py`、`catalog.sync_creator`、`pipeline.runner.run_pipeline`、`live.py` 的 `LiveWatcher`。
- 分支名建议：`issue-<N>-creator-monitor-profile`。
- 设计参考：对话结论；仓库 spec `docs/superpowers/specs/2026-05-20-media2text-douyin-design.md` 中 `creators` 表需在 PR 中同步更新文档（若改 schema）。

## 已确认决策（2026-05-20）

1. **`creator add` 移除 `--watch-live`**：收录不携带监控开关；仅通过 `creator monitor` 开启/关闭监控。
2. **对外守护命令为 `monitor watch`**：不保留 `live watch` 别名；文档与 CLI 中 `live watch` 全部替换为 `monitor watch`。
