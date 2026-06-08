---
issue: 231
epic: local-pipeline-refactor
github: 231
branch: issue-231-local-pipeline-refactor-pr2-live-worker
depends_on: [230]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR2：R2b Live Worker 任务化（LW-01..04）

## 背景

R1+R2a 交付 TaskScheduler + SessionRuntime 后，live 侧「开录 / STT / 重连 / finalize」应经 `monitor_tasks` 由 `MonitorExecutor` 消费，而非 Probe 内联 subprocess 或 enqueue。本 PR 实现规格 LW-01..04 四个 handler，为 R2c Reconciler 仅 `ensure_task` 铺路。

**参考**：规格 §LW · 计划 R2b Task 6

**依赖**：PR1（R1+R2a）已合并（SessionRuntime + async p0 drain）。

**阻塞**：R2c-1（#232）。

## 验收标准

### LW-01 — prepare_live_recording

- [x] `LiveRecordingCore.run_prepare_live_recording(creator_id, live_info=...)`：解析 stream、建 session、spawn ffmpeg
- [x] `monitor_executor._dispatch_task` 路由 `task_type=prepare_live_recording`
- [x] `test_prepare_live_recording_task` 通过

### LW-02 — start_streaming_stt

- [x] `run_start_streaming_stt(session_id)`：streaming 模式下启动 STT sidecar
- [x] `test_start_streaming_stt_task` 通过

### LW-03 — reconnect_recording

- [x] `run_reconnect_recording(session_id)`：包装 `_reconnect_segment`（ffmpeg 断线）
- [x] `test_reconnect_recording_task` 通过

### LW-04 — reconnect_streaming_stt

- [x] `run_reconnect_streaming_stt(session_id)`：包装 STT 断线重连路径
- [x] `test_reconnect_streaming_stt_task` 通过

### 集成

- [x] 所有 handler 经 `core_for_conn(conn)` 获取带 SessionRuntime 的 core
- [x] `tests/unit/test_live_worker_tasks.py` 全绿
- [x] 现有 `test_live_scheduler.py` / finalize 相关测试仍 PASS

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_live_worker_tasks.py tests/unit/test_live_scheduler.py tests/unit/test_task_scheduler.py -v
ruff check src/media2text/core/live/monitor_executor.py src/media2text/core/live/recording.py
```

## 非目标范围

- TaskReconciler（RR-01 自动 ensure prepare — R2c-1）
- `poll_active_session` 纯 obs（R2c-2）
- 删除 legacy `scan_and_start` from probe path（R2c-3）
- LW-05 content 类任务（已在 SlowTick/ContentObserve，本 Epic 不拆 download/transcribe）

## 依赖与顺序

- **依赖**：Local Pipeline Refactor PR1 已合并
- **冲突提示**：R2c-2 也改 `recording.py` — 必须先合并本 PR

## 实现备注

- 分支：`issue-231-local-pipeline-refactor-pr2-live-worker`
- GitHub Issue: [#231](https://github.com/oychao1988/media2text/issues/231)
