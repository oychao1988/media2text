## 背景

P0（#81 / PR #82 已 merge）已把 live poll、VOD、post-process 拆到三线程，**G5/G1 基础**已解锁。下播仍用 v1 的 **`offline_confirm_polls` 按 poll 次数**计 streak，首次 API offline **无 `live_ended` 通知**，G3/G4 未达标。

本工单实现 **Live Pipeline v2 — P1（墙钟 offline + 通知）**，对齐 spec v1.2 策略 **A：`offline_confirm_sec: 45`**。

**前置**

- P0 已合并：`MonitorScheduler` + `PostProcessExecutor`（main @ 1de67e0+）
- 设计：[docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md](docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md) §5–§7
- 计划 P1：[docs/superpowers/plans/2026-06-03-live-pipeline-v2.md](docs/superpowers/plans/2026-06-03-live-pipeline-v2.md) Task 4–6

**已锁定（D3）**

- G3：`live_ended` 在**首次 poll 检测到 offline** 后发出（最坏额外延迟 ≈ 一个 `live_poll_interval_sec`）
- 满 `offline_confirm_sec`（默认 45s）仍 offline 才 `_finalize_recording` → `recording_completed`

## 验收标准

### Task 4 — 配置与 session 列

- [ ] `LiveConfig.offline_confirm_sec: int = 45`；`config.example.yaml` 文档化；保留 `offline_confirm_polls` 仅作迁移说明（逻辑不再读 streak）
- [ ] `live_sessions` 迁移 `_migrate_live_sessions_v3`：`first_seen_live_at`、`recording_started_at`、`offline_since_at`、`platform_live_started_at`（nullable TEXT）
- [ ] `LiveSessionRow` + `LiveSessionRepo`：`set_offline_since` / `clear_offline_since`；create 时写入 `first_seen_live_at`、`recording_started_at`（ffmpeg 成功启动后）
- [ ] `tests/unit/test_config.py`、`tests/unit/test_storage.py`（或等价）覆盖新列与默认值

### Task 5 — 墙钟 offline（`recording.py`）

- [ ] `poll_active_recordings`：**不再** `increment_offline_streak` / `reset_offline_streak`
- [ ] API live → `clear_offline_since`（offline 误报恢复，不发用户通知）
- [ ] API offline 且 `recording_age >= min_recording_sec_before_offline_end`：
  - 若 `offline_since_at` 为空 → 写入 now + **一次** `live_ended` 通知
  - 若 `now - offline_since_at >= offline_confirm_sec` → `_finalize_recording`
- [ ] 新增 `tests/unit/test_offline_wall_clock.py`：首次 offline 只 notify 不 finalize；满 confirm_sec finalize；恢复 live 清空 offline_since
- [ ] 更新/替换 `tests/unit/test_live_recording_core.py` 中 streak 用例

### Task 6 — 新 notify kinds

- [ ] `EventKind`：`LIVE_ENDED`、`LIVE_START_FAILED`、`SUMMARIZE_COMPLETED`
- [ ] `NotifyEventsConfig` 默认 enabled；`config.example.yaml` `notify.events.*` 对齐
- [ ] `NotifyService._KIND_LABELS` 含新 kind
- [ ] `_start_recording` ffmpeg 早退 → `live_start_failed`
- [ ] `post_process.py` 摘要成功 → `summarize_completed`

### 质量

- [ ] `pytest tests/unit/test_offline_wall_clock.py tests/unit/test_live_recording_core.py tests/unit/test_config.py -v` 通过
- [ ] `pytest tests/ -v`、`ruff check src tests` 通过
- [ ] 更新 `CLAUDE.md`：墙钟 offline、`live_ended` 时序、P1 解锁 G3/G4

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"

ruff check src tests
pytest tests/unit/test_offline_wall_clock.py tests/unit/test_live_recording_core.py \
  tests/unit/test_config.py tests/unit/test_storage.py -v
pytest tests/ -v
```

## 非目标范围

- **P2**：`live_pipeline_events` 表、`live status|timeline|stats` CLI
- **P3**：`scan_concurrency`、adaptive `post_process_max_parallel`、`live stats` 聚合
- `live_resumed` 用户通知（仅 log）
- 改 VOD/archive/dynamic 业务逻辑

## 待确认问题

无（策略 A + D3 已在 spec 锁定）。

## 实现备注

- GitHub Issue: [#83](https://github.com/oychao1988/media2text/issues/83)
- 分支建议：`issue-83-live-pipeline-v2-p1`
- 依赖：P0 #81 已 merge main
