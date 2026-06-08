---
issue: 233
epic: local-pipeline-refactor
github: 233
branch: issue-233-local-pipeline-refactor-pr4-probe-guard
depends_on: [232]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR4：R2c-2 Probe 纯传感 + Guard + Content Due

## 背景

R2c-1 落地 Reconciler 后，Probe 线程必须变为**纯传感**：只写 DB obs/offline，禁止 enqueue、subprocess.Popen、`_start_recording`。本 PR 交付 `poll_active_session`、`ProbeExecutionGuard`、creators content due 列（D3），SlowTick 只 UPDATE due 不 enqueue。

**Epic 硬约束 G1**：`test_probe_never_enqueues` 在本 PR 合并前必须为绿（R2c-3 切流闸门）。

**参考**：规格 §I.3 Guard、§CP、§LP-02 · 计划 R2c-2 Tasks 11–12

**依赖**：PR3（Reconciler + StateWriter 最小集）已合并。

**阻塞**：PR5（默认 reconciler + legacy 删除）。

## 验收标准

### Task 11 — poll_active_session 纯 obs

- [x] `LiveRecordingCore.poll_active_session(row, creator, state=StateWriter)`：仅进程/API 检测 + StateWriter offline 语义
- [x] 删除路径内 `_enqueue_finalize`、`_reconnect_segment`、`_handle_stt_disconnect` 调用
- [x] `reconciler_enabled=False` 时 legacy `poll_active_recordings` 行为保留；True 时 delegate 纯 obs
- [x] `test_poll_active_writes_obs_only` 通过

### Task 12 — ProbeExecutionGuard

- [x] `probe_guard.py`：`enter_probe_tick` / `exit_probe_tick` / `record_violation`
- [x] Hook：`MonitorTaskRepo.enqueue/ensure_task`、`subprocess.Popen`、`_start_recording`
- [x] `test_probe_never_enqueues`：probe tick 内 enqueue/Popen 触发 strict 失败
- [x] `tests/unit/test_probe_guard.py` 全绿

### Task 12 Step 3–4 — Content due（D3）

- [x] creators 表：`vod_due_at`、`archive_due_at`、`dynamic_due_at`（TEXT ISO）
- [x] `SlowTickLoop` 删除 in-memory last_vod/archive/dynamic；到期只 `CreatorRepo.set_*_due`
- [x] `watcher._run_pipeline_tick` / `_run_dynamic_tick` 删除 direct enqueue；由 Reconciler `reconcile_content` ensure
- [x] `test_creators_content_due_columns` + reconciler content 用例通过

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_probe_guard.py tests/unit/test_poll_active_obs.py tests/unit/test_task_reconciler.py tests/unit/test_live_scheduler.py tests/unit/test_live_db_migration.py -v
ruff check src/media2text/core/live/probe_guard.py src/media2text/core/live/recording.py src/media2text/core/live/scheduler.py src/media2text/core/live/probe.py src/media2text/core/monitor/watcher.py src/media2text/core/live/task_reconciler.py src/media2text/core/storage/db.py src/media2text/core/storage/repos.py
```

## 非目标范围

- 平台 `run_once` probe-only 切流（R2c-3）
- `reconciler_enabled=true` 默认
- pipeline_phase / API 投影（R3a）
- notify outbox（R4）

## 依赖与顺序

- **依赖**：PR3 已合并
- **闸门**：合并 PR5 前 `test_probe_never_enqueues` 必须绿

## 实现备注

- 分支：`issue-233-local-pipeline-refactor-pr4-probe-guard`
- GitHub Issue: [#233](https://github.com/oychao1988/media2text/issues/233)
