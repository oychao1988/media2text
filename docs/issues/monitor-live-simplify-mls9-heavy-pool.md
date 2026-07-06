---
epic: monitor-live-simplify-2026-07-06
depends_on: [MLS-8]
github: 395
---

# MLS-9：HeavyPool（finalize + segment）

规格：§3 P3-3、D9

## 验收标准

- [x] `HeavyPool` 仅 wrap finalize + segment_process submit
- [x] `PostProcessExecutor` 独立；`live_lane_count==0` 逻辑保留
- [x] G5 压测：post-process 积压不拖 LiveTick

## 验证命令

```bash
pytest tests/unit/test_task_scheduler.py tests/unit/test_post_process_worker.py -v
```
