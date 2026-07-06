---
epic: monitor-live-simplify-2026-07-06
depends_on: [MLS-1, MLS-2]
---

# MLS-4：`monitor watch` 单轮对齐 daemon tick

规格：§3 P2-1,P2-3

## 验收标准

- [ ] `monitor watch`（无 `--daemon`）执行一轮 `LiveTick` + 一轮 `TaskSchedulerLoop.tick_once` 等价逻辑
- [ ] 删除 `watcher._drain_priority_zero_tasks` 或仅保留调试子命令
- [ ] 新增 `test_monitor_watch_single_round_matches_daemon_tick`

## 验证命令

```bash
pytest tests/unit/test_monitor_watcher.py tests/unit/test_monitor_daemon_integration.py -v
```

## 非目标

- 删 `platform/*/live.py` 的 `run_once`（MLS-5 可并行部分）
