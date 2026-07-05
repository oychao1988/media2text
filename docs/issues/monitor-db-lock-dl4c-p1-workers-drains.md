---
issue: 372
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/372
branch: issue-372-monitor-db-lock-dl4c
depends_on: [dl4b]
---

# DL-4c：P1 worker pools + drains 经 gateway

GitHub Issue: [#372](https://github.com/oychao1988/media2text/issues/372)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§4.4 P1、§6  
系列：DL-4b → **DL-4c**（可与 MH-4c 并行，依赖 DL-4b）

## 背景

P0 路径（scheduler + session repos）经 gateway 后，将 **post_process / segment / notify / desktop_events** worker 与 drain 统一为 gateway.write；延续 DL-2「LLM 期间无 DB」模式。

## 验收标准

### Task 1 — Worker pools

- [ ] `PostProcessExecutor` / `SegmentProcessExecutor`：job 内 read 短连接或 gateway.read；mutate 经 gateway.write
- [ ] `segment_watcher` / `segment_manifest` 裸 commit 改 gateway
- [ ] `MonitorExecutor` worker mark_done/fail 经 gateway（若 MH-4c 未覆盖）

### Task 2 — Drains

- [ ] `notify/drain.py`、`state_event_drain.py`：删除内部 `open_db`+`with_db_lock_retry` 双轨，改 `gateway.write(drain_once)`

### Task 3 — 测试

- [ ] `tests/unit/test_post_process_summarize_db.py` 仍 PASS
- [ ] `tests/unit/test_state_event_drain.py`、`tests/unit/test_api_state_event_drain.py` 仍 PASS
- [ ] 新增或扩展 segment gateway 单测

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_post_process_summarize_db.py tests/unit/test_state_event_drain.py tests/unit/test_api_state_event_drain.py tests/unit/test_segment_process_pool.py -v
ruff check src/media2text/core/live/post_process_pool.py src/media2text/core/live/segment_process_pool.py src/media2text/core/notify/drain.py src/media2text/api/services/state_event_drain.py
```

## 非目标范围

- Hermes SessionDB（→ DL-4d）
- 删除 `_sqlite_write_lock`（→ DL-4d）

## 依赖与顺序

- **依赖 DL-4b**；与 MH-4c 可并行
