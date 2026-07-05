---
issue: 368
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/368
branch: issue-368-monitor-db-lock-dl4b
depends_on: [dl4a]
---

# DL-4b：P0 repos + StateWriter + scheduler `write_batch`

GitHub Issue: [#368](https://github.com/oychao1988/media2text/issues/368)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§4.4–4.5、§6  
系列：DL-4a → **DL-4b** → MH-4a

## 背景

Gateway 骨架（DL-4a）就绪后，将 **最热写路径** 迁入 gateway：`LiveSessionRepo`、`MonitorTaskRepo`、`StateWriter`、`LiveSnapshotRepo`，以及 task-scheduler 每 tick 的 `write_batch(reconcile+claim)`。

## 验收标准

### Task 1 — WriteAwareRepo / P0 mutators

- [ ] `LiveSessionRepo`、`MonitorTaskRepo`、`StateWriter` 全部 mutating 方法经 `gateway.write` 或 `WriteAwareRepo._mutate`
- [ ] `LiveSnapshotRepo.upsert` / `touch_probe` 改经 gateway；**删除** `snapshot.py` 的 `_snapshot_write_lock`
- [ ] `BEGIN IMMEDIATE` 仅出现在 gateway writer 线程内（`set_offline_since` / `clear_offline_since`）

### Task 2 — TaskSchedulerLoop

- [ ] `TaskSchedulerLoop._run`：`write_batch(tick_once)` 单事务 reconcile + claim + drain 声明（I/O 仍在 worker，claim 在 batch 内）
- [ ] 日志 `task_scheduler_db_locked` 在单元压测 30s 内 **0 次**（mock 11 creators + scheduler）

### Task 3 — 测试

- [ ] 扩展 `tests/unit/test_task_scheduler.py`：gateway mock 验证 batch 单 commit
- [ ] `tests/unit/test_live_db_lock_probe_snapshot.py` 仍 PASS（snapshot 经 gateway）
- [ ] 新增 `tests/unit/test_state_writer_gateway.py`：`write_obs` / `set_offline_since` 经 gateway

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_db_write_gateway.py tests/unit/test_task_scheduler.py tests/unit/test_live_db_lock_probe_snapshot.py tests/unit/test_state_writer_gateway.py tests/unit/test_live_snapshot_upsert.py -v
ruff check src/media2text/core/live/task_scheduler.py src/media2text/core/live/state_writer.py src/media2text/core/storage/repos.py src/media2text/core/live/snapshot.py
```

## 非目标范围

- post_process / segment / notify drains（→ DL-4c）
- 删除 `_sqlite_write_lock`（→ DL-4d）
- MonitorWatcher._conn 删除（→ MH-4b）

## 依赖与顺序

- **依赖 DL-4a 合并**；阻塞 MH-4a、MH-4b
