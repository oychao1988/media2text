---
issue: 283
epic: live-segment-media-gap-fix
github: 283
branch: issue-283-live-segment-gap-g3
depends_on: [274]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Gap G3：segment_process 失败重试 + Reconciler RR

## 背景

Spec §6 要求 Tier-1 Reconciler：

- `segment_process_jobs` **failed** → 重置 `pending`（上限 `max_attempts`）
- `live_session_parts` stuck `uploading` → stale reset

**现网 gap：**

- `run_segment_process_job` 失败仅 `mark_failed`；**无** failed→pending 自动重试。
- `SegmentProcessJobRepo` 仅有 `reset_stale_running()`（`running` 超时），在 `segment_process_pool.drain_pending` 调用；**不处理** `failed`。
- `task_reconciler.reconcile_live` 未触及 segment 任务。
- 无 CLI `segment-process retry`（对比已有 `post-process retry`）。
- part 状态机无 `uploading` / `failed` 行级态（spec §4 有，实现简化为 `closed→uploaded→local_deleted`）— 本 Issue **不要求** 补全中间态，仅保证 job 可重试。

**参考**

- [design spec §6、Failure modes「upload 失败」](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- `segment_manifest.py`、`segment_process_pool.py`、`task_reconciler.py`

**依赖**：#274

## 验收标准

### Task 1 — 配置

- [x] `live.segment_pipeline.max_attempts`（默认 `5`）写入 `LiveSegmentPipelineConfig`、`config.example.yaml`

### Task 2 — Reconciler / drain 重试

- [x] 新增 `SegmentProcessJobRepo.reset_failed_to_pending(*, max_attempts)`：`status=failed` 且 `attempts < max_attempts` → `pending`，保留 `last_error`
- [x] 在 `TaskSchedulerLoop.tick_once`（segment drain 前）或 `reconcile_live` 末尾调用上述 reset（与 `post_process` stale reset 模式一致）
- [x] `attempts >= max_attempts` 的 job 保持 `failed`，打 structlog warning

### Task 3 — CLI（可选但推荐）

- [x] `media2text segment-process retry <job_id> --json`：将指定 `failed` job 重置为 `pending`（无视 attempts，单次人工救急）
- [x] 或 `media2text segment-process run [--limit N] --json` 消化 pending（若已有则文档化即可）

### Task 4 — 单测

- [x] `tests/unit/test_segment_process_retry.py`（或扩展现有 `test_segment_process.py`）：
  - failed job + attempts&lt;max → reconcile 后变 pending 且可被 claim
  - attempts≥max → 保持 failed
- [x] 回归：`pytest tests/unit/test_segment_process.py tests/unit/test_task_scheduler_segment_order.py -v`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_segment_process.py tests/unit/test_task_scheduler_segment_order.py -v
pytest tests/unit/test_segment_process_retry.py -v
ruff check src/media2text/core/live/segment_manifest.py src/media2text/core/live/task_scheduler.py
```

## 非目标范围

- `live_session_parts.state=uploading` 细粒度状态（可选 follow-up）
- 修改 aliyundrive 上传协议 / rolling_cleanup 规则
- 段级 compress fallback（另开单）

## 依赖与顺序

- **依赖**：#274
- **建议分支**：`issue-283-live-segment-gap-g3`

## GitHub

- Issue: [#283](https://github.com/oychao1988/media2text/issues/283)
