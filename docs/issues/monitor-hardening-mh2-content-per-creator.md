---
issue: 346
epic: monitor-hardening-2026-06-26
github: 346
branch: issue-346-monitor-hardening-mh2
depends_on: []
---

# MH-2：per-creator 内容同步 — 单博主在录不暂停全员 VOD

GitHub Issue: [#346](https://github.com/oychao1988/media2text/issues/346)  
Epic：**Monitor Hardening**（2026-06-26）  
系列：MH-1 / **MH-2** / MH-3 可并行 → MH-4

## 背景

`TaskSchedulerLoop.tick_once` 在 **任一** `live_sessions` active 时将 `content_parallel=0` 并 `MonitorTaskRepo.release_running_content_tasks()`，导致博主 A 长直播期间博主 B/C 的 `sync_catalog` / `download` / `sync_dynamic` 全部饥饿。

`reconcile_content` 已 per-creator 跳过有 active session 的博主，但 scheduler drain 与 supervisor shutdown 仍为全局 pause，行为不一致。

**参考**

- Eng review D2；outside voice：需 claim filter + supervisor 对齐
- 代码：`src/media2text/core/live/task_scheduler.py:107-116`、`src/media2text/core/runtime/supervisor.py`（`_reset_stale_queue_work`）

## 验收标准

### Task 1 — Scheduler 不再全局 `content_parallel=0`

- [x] 存在 active session 时：**不**将 content pool limit 置 0
- [x] `MonitorTaskRepo.claim_pending`（或 drain 前过滤）：跳过 `creator_id` 当前有 active `live_sessions` 的 content 任务（priority ≥ 10）
- [x] **不**调用全局 `release_running_content_tasks()`；改为仅 release 属于「有 active session 的 creator_id」的 running content 任务（新增 repo 方法或等价 SQL）
- [x] 单元测：creator A recording + creator B `sync_catalog` pending → B 的任务仍被 claim/submit

### Task 2 — Supervisor / work_queue 对齐

- [x] `MonitorSupervisor._reset_stale_queue_work` 与 `api/services/work_queue.py` 中同类逻辑改为 per-creator（与 Task 1 语义一致），避免 shutdown 误杀无关博主 content 任务
- [x] `test_monitor_supervisor` 或新测覆盖「A 在录时 B 的 pending sync 不被 release」

### Task 3 — 日志与回归

- [x] 移除或替换误导性全局 pause 日志；保留 `content_tasks_released_for_live` 时 `creator_id` 粒度
- [x] 现有 `test_task_scheduler` 中与 global pause 相关的断言更新为 per-creator 行为

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_task_scheduler.py tests/unit/test_monitor_supervisor.py tests/unit/test_task_reconciler.py -v
ruff check src/media2text/core/live/task_scheduler.py src/media2text/core/runtime/supervisor.py src/media2text/core/storage/repos.py
```

## 非目标范围

- live lane defer post_process（MP-3 已交付，勿改语义）
- Playwright 槽位数调整
- Desktop UI 变更

## 依赖与顺序

- **无硬依赖**；与 MH-1 可并行
- 建议在 MH-4 集成测之前合并
