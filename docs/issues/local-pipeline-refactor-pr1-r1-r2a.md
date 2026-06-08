---
issue: 230
epic: local-pipeline-refactor
github: 230
branch: issue-230-local-pipeline-refactor-pr1-r1-r2a
depends_on: []
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR1：R1+R2a 异步 finalize + TaskScheduler + SessionRuntime

## 背景

`monitor watch --daemon` 当前在 `LiveTickLoop` 内同步调用 `monitor_pool.drain_priority_zero()`，finalize/remux 会阻塞 live poll（G5 违反）。Execution Engine v2 将 Probe 与 Worker 解耦：LiveTick 只做 LP-01/02/03 传感，finalize 由独立 `TaskSchedulerThread` 异步 drain。

**Eng Review D2：R1 与 R2a 必须捆绑同一 PR**——禁止单独合并「删 sync drain」而不交付 Scheduler drain，否则 finalize 任务会积压。

**参考**

- 规格：[2026-06-08-m2t-local-pipeline-refactor-design.md](../superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md) §I、§LP、§SR
- 计划：R1+R2a Tasks 1–5b（[2026-06-09-m2t-local-pipeline-refactor.md](../superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md)）

**前置**：Live Pipeline v2（#81–#87）已交付；`monitor_tasks` 表与 `MonitorExecutor` 已存在。

**阻塞**：#231（R2b）、整个 R2c 系列。

## 验收标准

### Task 1 — 移除 LiveTick 内联 finalize drain

- [x] `LiveTickLoop._run` 不再调用 `monitor_pool.drain_priority_zero`
- [x] `test_live_tick_not_blocked_by_slow_finalize`：mock 慢 `run_once` 时 tick 不阻塞且 `drain_priority_zero` 未被调用
- [x] `test_finalize_enqueued_once_and_drained_inline` 改为仅断言 poll enqueue（drain 归 Scheduler）

### Task 2 — MonitorConfig 新字段

- [x] `scheduler_interval_sec`（默认 1）、`live_lane_min_claim_per_tick`（默认 1）、`probe_parallelism`（默认 4）、`reconciler_enabled`（默认 false）、`live_worker_max_parallel`（默认 1）、`probe_tick_budget_sec`、`probe_http_timeout_sec`
- [x] `config.example.yaml` `monitor:` 段同步
- [x] `test_monitor_scheduler_config_defaults` 通过

### Task 3 — TaskSchedulerThread

- [x] 新建 `task_scheduler.py`：`TaskSchedulerLoop.tick_once` — p0 drain → live workers → post_process
- [x] `MonitorExecutor.claim_and_submit_priority_zero`（async submit，非 sync drain）
- [x] `MonitorScheduler` 三线程：`live-probe` + `task-scheduler` + `slow-tick`；SlowTick 不再 inline `monitor_pool.drain_pending`
- [x] `live_worker_max_parallel` 驱动 MonitorExecutor pool（D5）
- [x] `test_task_scheduler_drains_priority_zero_async` 通过

### Task 4 — 每线程 open_db

- [x] Probe 与 Scheduler 各自 `open_db()`，禁止跨线程写 `watcher._conn`
- [x] `test_conn_per_thread_no_shared_watcher_conn` + 100-tick stress 通过

### Task 5 — LiveProbe budget / parallel（LP-03）

- [x] `probe.py` 或 inline：tick budget + 并行 scan（`probe_parallelism`）
- [x] 现有 `test_live_scheduler.py` 相关用例仍 PASS

### Task 5b — SessionRuntime（D1）

- [x] 新建 `session_runtime.py`：共享 `_processes` / `_stt_sessions`
- [x] `MonitorWatcher` 持单例 `SessionRuntime`；`core_for_conn(conn)` 注入 runtime
- [x] Worker 每任务 `open_db()` + 新建 `LiveRecordingCore(..., runtime=...)`
- [x] `test_session_runtime_shared_across_worker_threads` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_live_scheduler.py tests/unit/test_task_scheduler.py \
  tests/unit/test_session_runtime.py tests/unit/test_offline_wall_clock.py -v
ruff check src/media2text/core/live/scheduler.py \
  src/media2text/core/live/task_scheduler.py \
  src/media2text/core/live/session_runtime.py \
  src/media2text/core/live/monitor_executor.py \
  src/media2text/core/monitor/watcher.py \
  src/media2text/core/config.py
media2text doctor --json
```

## 非目标范围

- TaskReconciler / `reconciler_enabled=true` 默认（R2c-3）
- LW-01..04 handler（#227）
- `obs_*` 列、StateWriter、ProbeExecutionGuard（R2c）
- `pipeline_phase`、notify outbox（R3/R4）
- download/transcribe 任务拆分（Spec Epic 外）

## 依赖与顺序

- **依赖**：Live Pipeline v2 已合并
- **必须**：本 PR 为 R2b/R2c 唯一入口；勿拆成「仅删 drain」子 PR

## 实现备注

- 分支：`issue-230-local-pipeline-refactor-pr1-r1-r2a`
- GitHub Issue: [#230](https://github.com/oychao1988/media2text/issues/230)
