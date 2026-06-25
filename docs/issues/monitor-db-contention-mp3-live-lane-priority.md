---
issue: 336
epic: monitor-db-contention-2026-06-25
github: 336
branch: issue-336-monitor-db-mp3-live-lane-priority
depends_on: [334]
---

# MP-3：Live lane 优先 — 待开录时暂停 post_process drain

GitHub Issue: [#336](https://github.com/oychao1988/media2text/issues/336)  
Epic：**Monitor DB Contention**（2026-06-25）  
系列：MP-1 → MP-2 → **MP-3**（可与 MP-2 并行，依赖 MP-1）

## 背景

`TaskSchedulerLoop` 每秒 `reconcile_live` + `post_pool.drain_pending` 并行。当博主已开播但 `prepare_live_recording` 因 DB 锁失败时，post_process summarize 仍占用 worker 与 DB 连接，加剧 live lane 饿死。

已有 precedent：`active_sessions` 存在时 `content_parallel=0` 并 `release_running_content_tasks()`，但 **post_process 无类似让路**。

## 验收标准

### Task 1 — `live_lane_needs_priority(conn, cfg)`

- [ ] 新建 helper（`core/live/live_lane.py` 或 `task_scheduler` 模块内）：返回 True 当任一 monitored creator 满足：
  - `creator_live_snapshots.is_live=1` 且无 `live_sessions` active recording；或
  - 存在 `prepare_live_recording` 的 `pending`/`running` monitor_task
- [ ] 单元测试覆盖「在播无 session」「有 pending prepare」两场景

### Task 2 — scheduler 跳过 post_process drain

- [ ] `TaskSchedulerLoop.tick_once`：若 `live_lane_needs_priority` → **跳过** `_post_pool.drain_pending`（segment_pool 仍可 drain）
- [ ] log info `post_process_deferred_for_live_lane`（structlog，含计数）
- [ ] `test_task_scheduler_defers_post_process_when_live_pending` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_task_scheduler.py tests/unit/test_live_lane_priority.py -v
ruff check src/media2text/core/live/task_scheduler.py src/media2text/core/live/live_lane.py
```

## 非目标范围

- 完全禁用 post_process（仅临时 defer drain）
- 调整 post_process worker 数
- MP-2 单 owner 逻辑

## 依赖与顺序

- **依赖**：#334（dedupe 减少 post_process 积压）
- **与 #335 可并行**
