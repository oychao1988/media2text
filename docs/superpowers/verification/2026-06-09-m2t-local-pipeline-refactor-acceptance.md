# Local Pipeline Refactor — Epic 验收

规格：[2026-06-08-m2t-local-pipeline-refactor-design.md](../specs/2026-06-08-m2t-local-pipeline-refactor-design.md)  
计划：[2026-06-09-m2t-local-pipeline-refactor.md](../plans/2026-06-09-m2t-local-pipeline-refactor.md)

> PR5（R2c-3）合并时填写 G1–G5；PR8（R4）合并时填写 L6。

| ID | 验收项 | 命令/证据 | PR5 | PR8 |
|----|--------|-----------|-----|-----|
| G1 | Probe 零 enqueue/subprocess | `pytest tests/unit/test_probe_guard.py -v` | [x] | |
| G1′ | 开录 P95 ≤30s | `media2text live stats --days 1 --json` + pipeline_events | [ ] 人工/生产 | |
| G3/G4 | offline→live_ended；confirm+finalize ≤60s | unit + `tests/e2e/test_live_pipeline_reconciler.py` | [x] unit/E2E mock | |
| G5 | Content 不拖 Probe | `test_live_tick_runs_while_slow_tick_blocks` | [x] | |
| L6 | notify outbox only | `pytest tests/unit/test_notify_outbox.py -v` | | [x] |

## E2E（R2c-3 闸门）

- [x] `tests/e2e/test_live_pipeline_reconciler.py`：mock is_live → prepare → offline → finalize

## Epic verify

```bash
python scripts/epic_verify.py local-pipeline-refactor
```
