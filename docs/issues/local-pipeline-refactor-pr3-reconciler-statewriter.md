---
issue: 232
epic: local-pipeline-refactor
github: 232
branch: issue-232-local-pipeline-refactor-pr3-reconciler
depends_on: [231]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR3：R2c-1 Schema + Reconciler + StateWriter 最小集

## 背景

Execution Engine v2 核心约束：**任务仅由 TaskReconciler `ensure_task` 创建**；session 观测字段 `obs_*` 与 offline 语义经 `StateWriter` 单写口。本 PR 落地 DB 迁移、Repo 扩展、Reconciler RR-01..05 / RC-01 骨架、Scheduler tick 顺序（reconcile → drain，D4），**默认 `reconciler_enabled=false`** 以便 shadow 联调。

**参考**：规格 §RR、§RC、§StateWriter · 计划 R2c-1 Tasks 7–10

**依赖**：PR2（LW handlers）已合并。

**阻塞**：PR4（Probe Guard + content due）。

## 验收标准

### Task 7 — live_sessions obs_* 迁移

- [x] `_migrate_live_sessions_v5`：`obs_ffmpeg_alive`、`obs_stt_alive`、`obs_still_live`、`obs_polled_at`
- [x] `LiveSessionRow` 扩展对应字段
- [x] `test_live_sessions_obs_columns` 通过

### Task 8 — MonitorTaskRepo.ensure_task + cancel_pending

- [x] `ensure_task` 幂等（pending dedupe）；running 时不重复
- [x] `cancel_pending(dedupe_key)` 仅取消 pending
- [x] `has_active_dedupe` 供 Reconciler flash recovery
- [x] `tests/unit/test_monitor_task_repo.py` 扩展通过

### Task 9 — StateWriter 最小集

- [x] `state_writer.py`：`write_obs`、`set_offline_since`、`clear_offline_since`
- [x] offline 双写 obs + `record_event` + `enqueue_creator_updated`
- [x] `tests/unit/test_state_writer.py` 通过

### Task 10 — TaskReconciler

- [x] `task_reconciler.py`：`reconcile_live`（RR-01 prepare、RR-02 finalize + flash cancel、RR-03..05 obs 驱动 reconnect/STT）
- [x] `reconcile_content` 骨架（读 creator due — 完整 due 列在 PR4）
- [x] `TaskSchedulerLoop.tick_once`：`reconciler_enabled` 时 reconcile_live → reconcile_content → drain（D4）
- [x] 可选 `reconciler_log_only` shadow 模式
- [x] `test_scheduler_reconcile_prepare_when_live_no_session`、`test_scheduler_reconcile_finalize_when_offline_confirmed`、`test_offline_flash_recovery_cancels_pending_finalize`、`test_scheduler_tick_order_reconcile_before_drain` 通过

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_live_db_migration.py tests/unit/test_monitor_task_repo.py tests/unit/test_state_writer.py tests/unit/test_task_reconciler.py tests/unit/test_task_scheduler.py -v
ruff check src/media2text/core/live/task_reconciler.py src/media2text/core/live/state_writer.py src/media2text/core/storage/db.py src/media2text/core/storage/repos.py
```

## 非目标范围

- `reconciler_enabled=true` 默认（R2c-3）
- ProbeExecutionGuard / probe 零 enqueue（R2c-2）
- creators `*_due_at` 迁移与 SlowTick 改造（R2c-2）
- notify_events outbox（R4）
- StateWriter 全量收口 + CI grep（R3b）

## 依赖与顺序

- **依赖**：PR2 已合并
- **配置**：合并后 `reconciler_enabled` 仍为 false；生产切流在 PR5

## 实现备注

- 分支：`issue-232-local-pipeline-refactor-pr3-reconciler`
- GitHub Issue: [#232](https://github.com/oychao1988/media2text/issues/232)
