---
issue: 345
epic: monitor-hardening-2026-06-26
github: 345
branch: issue-345-monitor-hardening-mh1
depends_on: []
---

# MH-1：SlowTick due_at 唤醒 + poll 单点 + live_lane SQL

GitHub Issue: [#345](https://github.com/oychao1988/media2text/issues/345)  
Epic：**Monitor Hardening**（2026-06-26，`/plan-eng-review` 监控逻辑审查）  
系列：**MH-1** → MH-2 / MH-3（可并行）→ MH-4

## 背景

`monitor watch --daemon` 的 `SlowTickLoop` 当前每 **1 秒** `open_db` 并扫描全部 `content_sync_enabled` 博主标记 `*_due_at`，与配置的 `vod_poll_interval_sec`（默认 300s）等语义不一致，且与 `live-probe`、`task-scheduler` 叠加放大 SQLite 锁竞争（2026-06-25 MP Epic 根因之一）。

`live_lane_priority_count` 每秒 Python 遍历全部 monitored 博主查 snapshot/session，博主规模增大后成为 hidden hotspot。

**参考**

- Eng review D1（due_at 唤醒）、D6（DRY intervals）、D10（SQL COUNT）
- Spec：[monitor-daemon-observe-execute-design](../superpowers/specs/2026-06-05-monitor-daemon-observe-execute-design.md) §3.2 ContentObserve 各自间隔
- 代码锚点：`src/media2text/core/live/scheduler.py`（`SlowTickLoop`）、`src/media2text/core/live/live_lane.py`

## 验收标准

### Task 1 — SlowTick 按 `min(*_due_at)` 唤醒

- [x] `SlowTickLoop._run`：计算 monitored + `content_sync_enabled` 博主的最小 `vod_due_at` / `archive_due_at` / `dynamic_due_at`（NULL 视为「可立即标记」）
- [x] `threading.Event.wait(timeout=…)` 使用 `max(1, min_seconds_until_due)`，无 due 行时 fallback 到 `min(vod_poll, archive_poll, dynamic_poll)`
- [x] **distill**（`CreatorAgentJobPool.drain_pending`，现 300s）保持独立计时，不与 content due sleep 混为一谈
- [x] 单元测：`test_slow_tick_waits_until_next_due`（mock monotonic / 短 poll 配置，断言 slow-tick 在 due 前不重复 mark）

### Task 2 — DRY poll interval helpers

- [x] 新建 `src/media2text/core/monitor/intervals.py`（或等价模块）：`live_poll_interval(cfg)`、`vod_poll_interval(cfg)`、`bilibili_archive_poll_sec(cfg)`、`bilibili_dynamic_poll_sec(cfg)`
- [x] 替换 `watcher.py`、`scheduler.py`、`task_reconciler.py` 中重复的 `_bilibili_archive_poll_sec` 等
- [x] 单测覆盖 B 站 archive fallback 链

### Task 3 — `live_lane_priority_count` SQL 化

- [x] 用 1–2 条 SQL（或 repo 方法）替代 Python 全表扫：`(is_live=1 AND no active recording)` COUNT + `prepare_live_recording` pending/running COUNT
- [x] 结果与现有 `test_live_lane_priority.py` 三场景等价
- [x] `test_live_lane_priority` 仍 PASS；可增 `test_live_lane_count_sql_equivalence`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_live_scheduler.py tests/unit/test_live_lane_priority.py tests/unit/test_task_scheduler.py tests/unit/test_monitor_intervals.py -v -k "slow_tick or live_lane"
ruff check src/media2text/core/live/scheduler.py src/media2text/core/live/live_lane.py src/media2text/core/monitor/ src/media2text/core/live/task_reconciler.py
```

## 非目标范围

- per-creator content pause（MH-2）
- prepare Playwright / hybrid conn（MH-3）
- `open_db()` migration 单次化（MH-5）
- 改 `reconcile_content` / `TaskSchedulerLoop` drain 顺序

## 依赖与顺序

- **无前置**；与 MH-2、MH-3、MH-5 可并行开发
- **建议先于** MH-4 集成测（减少 flaky）
