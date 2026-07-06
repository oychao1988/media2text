---
epic: monitor-live-simplify-2026-07-06
github: 394
depends_on: [MLS-7]
---

# MLS-8：`live.inline_decisions` 内联开录/下播

规格：§3 P3-2、D4、D8、D13

## 验收标准

- [x] 配置 `live.inline_decisions`（默认 false，灰度后 true）
- [x] true 时 `LiveLoop` 内联 decide；删除 `reconcile_live` 直播部分
- [x] `test_live_loop_inline_prepare_no_duplicate` 防 double-prepare
- [x] G1 benchmark 不退化

## 验证命令

```bash
pytest tests/unit/test_g1_recording_latency.py tests/unit/test_task_reconciler.py tests/unit/test_live_loop_inline_prepare.py -v
```
