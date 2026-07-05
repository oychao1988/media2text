---
issue: 371
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/371
branch: issue-371-monitor-session-sm-mh4c
depends_on: [mh4b]
---

# MH-4c：Worker dispatch 去 MH-3 — finalize/prepare/reconnect

GitHub Issue: [#371](https://github.com/oychao1988/media2text/issues/371)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§5.4  
系列：MH-4b → **MH-4c** → MH-4d

## 背景

MH-3（#347）hybrid：`worker conn` claim + `watcher._conn` core。MH-4b 已删长连接；本 Issue worker 改 **registry + SessionStateMachine**，删除 `_core_for_task(... watcher._conn ...)`.

## 验收标准

### Task 1 — monitor_executor

- [ ] 删除 `_core_for_task` 的 `watcher._conn` 绑定
- [ ] `finalize` / `prepare_live_recording` / `reconnect_*` / `start_streaming_stt` dispatch → `SessionStateMachineRegistry`
- [ ] worker `open_db` 仅用于已废弃路径的清理；mark_done/fail 经 gateway

### Task 2 — bootstrap STT

- [ ] `bootstrap_streaming_stt_on_daemon_start` 用 registry + runtime，无 watcher._conn

### Task 3 — 测试

- [ ] 扩展 `tests/unit/test_live_worker_tasks.py`：finalize/prepare 不访问 watcher._conn
- [ ] `tests/unit/test_monitor_executor_no_mh3.py` 新增

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_live_worker_tasks.py tests/unit/test_monitor_executor_no_mh3.py tests/unit/test_task_scheduler.py -v -k "finalize or prepare or worker"
ruff check src/media2text/core/live/monitor_executor.py src/media2text/core/monitor/watcher.py
```

## 非目标范围

- `LiveRecordingCore` 大删（→ MH-4d）
- P1 worker pools gateway（→ DL-4c，可并行但本 Issue 不依赖）

## 依赖与顺序

- **依赖 MH-4b**；阻塞 MH-4d
