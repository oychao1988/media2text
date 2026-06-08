---
issue: 248
epic: local-pipeline-spec-gap-fix
github: 248
branch: issue-248-local-pipeline-gap-fix-gf3
depends_on: [247]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md
---

# Local Pipeline Gap Fix GF-3：SlowTick 独立 conn + 死代码清理

## 背景

Gap 审计：

1. **I.6**：`SlowTickLoop` 经 `MonitorWatcher._conn` / `self._creators` 写 due clock，违反每线程 `open_db()`。
2. 主路径无调用方 legacy：`scan_and_start`、`_handle_ffmpeg_exit`、`_enqueue_finalize`、`drain_priority_zero`。

本 Issue 对应 gap-fix **GF-3**。Eng Review **D4B**：Task 9 `run_once` 对齐 **不做**，仅文档标注 debug-only。

**参考**

- 规格 §I.6
- 计划 GF-3 Tasks 7–9（Task 9 仅文档）

**依赖**：#247 建议先合并（降低 `live/` 并发冲突）。

## 验收标准

### Task 7 — SlowTick 独立 conn

- [x] `_run_vod_tick` / `_run_archive_tick` / `_run_dynamic_tick` 接受 `conn` 参数
- [x] `SlowTickLoop._run` 内 `open_db()` → 传入 watcher tick → `close`
- [x] Daemon 路径不再经 `watcher._creators` 写 due
- [x] `test_conn_per_thread_no_shared_watcher_conn` 仍 PASS
- [x] `test_slow_tick_uses_own_conn_not_watcher_conn` 通过

### Task 8 — 删除 legacy 代码

- [x] `rg 'scan_and_start|_handle_ffmpeg_exit|drain_priority_zero|_enqueue_finalize' src/` 无匹配
- [x] 删除或迁移 `scan_and_start` 相关单测至 `test_legacy_*` 或删除
- [x] `pytest tests/unit/ -v -k live` 全绿

### Task 9 — run_once（文档 only，D4B）

- [x] README 或 `monitor watch` help：无 `--daemon` 为 debug-only，不保证 Execution Engine 语义
- [ ] **不**实现 `run_scheduler_round()` 抽取

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_task_scheduler.py tests/unit/test_live_scheduler.py tests/unit/test_poll_active_obs.py -v
pytest tests/unit/ -v -k live --tb=short -q
rg 'scan_and_start|_handle_ffmpeg_exit|drain_priority_zero|_enqueue_finalize' src/ && exit 1 || true
ruff check src/media2text/core/live/scheduler.py src/media2text/core/monitor/watcher.py src/media2text/core/live/recording.py
```

## 非目标范围

- StateWriter 收口 snapshot/events（#249）
- Notify outbox（#247）
- Reconciler RC-04（#246）
- `run_once` 与 daemon 语义完全对齐（YAGNI）

## 依赖与顺序

- **依赖**：#247 建议先合并
- **与 #249**：GF-4 touches `recording.py`；建议本单先合并或协调 rebase

## 实现备注

- 分支：`issue-248-local-pipeline-gap-fix-gf3`
- GitHub Issue: [#248](https://github.com/oychao1988/media2text/issues/248)
