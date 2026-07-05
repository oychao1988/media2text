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

- [ ] `poll_active_recordings` / `poll_active_session` 旧实现删除或 <50 行 delegate
- [ ] `_finalize_recording_*` 核心逻辑在 `SessionStateMachine.run_finalize`
- [ ] `LiveRecordingCore` 无 `self._conn` 字段
- [ ] MH-3 注释与 hybrid 文档标记 superseded

### Task 2 — 文档

- [ ] `CLAUDE.md` monitor 线程模型更新（gateway + registry）
- [ ] `docs/issues/monitor-hardening-mh3-prepare-playwright-conn.md` 顶部注明 superseded

### Task 3 — 回归

- [ ] `pytest tests/unit/test_streaming_finalize.py tests/unit/test_streaming_stt.py tests/unit/test_live_worker_tasks.py -v` PASS
- [ ] `recording.py` 行数较 MH-4c 前显著减少（目标 -30% 以上 poll/finalize 相关）

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
