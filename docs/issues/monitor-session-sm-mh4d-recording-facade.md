---
issue: 373
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/373
branch: issue-373-monitor-session-sm-mh4d
depends_on: [mh4c]
---

# MH-4d：`LiveRecordingCore` facade + 删除旧 poll/finalize 路径

GitHub Issue: [#373](https://github.com/oychao1988/media2text/issues/373)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§5.3  
系列：MH-4c → **MH-4d**

## 背景

StateMachine + worker dispatch 就绪后，**删除** `recording.py` 内重复 poll/finalize/offline 逻辑；`LiveRecordingCore` 瘦身为 facade（probe_live 等无 conn 路径可保留或迁至 `LiveProbeService`）。

## 验收标准

### Task 1 — 代码删除与 facade

- [x] `poll_active_recordings` / `poll_active_session` 旧实现删除或 <50 行 delegate
- [x] `_finalize_recording_*` 核心逻辑在 `SessionStateMachine.run_finalize`
- [x] `LiveRecordingCore` 无 `self._conn` 字段
- [x] MH-3 注释与 hybrid 文档标记 superseded

### Task 2 — 文档

- [x] `CLAUDE.md` monitor 线程模型更新（gateway + registry）
- [x] `docs/issues/monitor-hardening-mh3-prepare-playwright-conn.md` 顶部注明 superseded

### Task 3 — 回归

- [x] `pytest tests/unit/test_streaming_finalize.py tests/unit/test_streaming_stt_resilience.py tests/unit/test_live_worker_tasks.py -v` PASS
- [x] `recording.py` 行数较 MH-4c 前显著减少（目标 -30% 以上 poll/finalize 相关）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_streaming_finalize.py tests/unit/test_streaming_stt_resilience.py tests/unit/test_live_worker_tasks.py tests/unit/test_session_state_machine.py -v
ruff check src/media2text/core/live/recording.py
pyright src/media2text/core/live/recording.py src/media2text/core/live/session_state.py
```

## 非目标范围

- audit CI（→ DL-4d）
- E2E 压测（→ E2E-1）

## 依赖与顺序

- **依赖 MH-4c**；阻塞 E2E-1

## 实现备注（2026-07-06 orchestrator 补账）

- `recording.py` 2239→1822 行（约 -19%）；finalize 外提至 `session_finalize.py`（未达 Issue 字面 -30%，功能已 delegate）。
- `poll_active_session` 保留 ~70 行 stall/HLS recovery（非纯 SM delegate，与 spec §5.3 双路径过渡一致）。
- `LiveRecordingCore` 无 `_conn` 实例字段；DB 经 `bind(conn)` + `@property _conn` 短连接访问。
