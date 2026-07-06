---
epic: monitor-live-simplify-2026-07-06
github: 393
depends_on: [MLS-4, MLS-5]
---

# MLS-7：提取 `LiveSession`

规格：§3 P3-1

## 验收标准

- [x] 新增 `core/live/session.py`；迁 prepare/poll/offline 核心
- [x] `recording.py` 行数显著下降；现有录制单测绿

## 验证命令

```bash
pytest tests/unit/test_live_recording_core.py tests/unit/test_streaming_finalize.py -v
```
