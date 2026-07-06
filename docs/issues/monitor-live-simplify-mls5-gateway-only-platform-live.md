---
epic: monitor-live-simplify-2026-07-06
depends_on: [MLS-1]
---

# MLS-5：平台 live gateway-only 写路径

规格：§3 P2-2,P2-4

## 验收标准

- [ ] `douyin/live.py`、`bilibili/live.py` 去掉 `with_db_lock_retry`；poll/finalize 经 `WriteGateway`
- [ ] 删除 `run_once`；调用方改 `run_probe_observe` + registry
- [ ] `test_db_lock_stress` / `tests/stress/test_db_lock_stress.py` 通过

## 验证命令

```bash
pytest tests/unit/test_monitor_watcher.py tests/stress/test_db_lock_stress.py -v -m db_stress
```
