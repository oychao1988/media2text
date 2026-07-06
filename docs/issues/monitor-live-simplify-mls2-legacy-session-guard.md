---
epic: monitor-live-simplify-2026-07-06
github: 388
branch: issue-388-mls2-legacy-session-guard
depends_on: [MLS-1]
---

# MLS-2：禁止新 legacy live session

GitHub Issue: [#388](https://github.com/oychao1988/media2text/issues/388)

规格：§3 P1-5、D7

## 背景

`pipeline_mode=legacy` 已 deprecated；新录制应强制 `streaming`。旧 DB 行仍可只读 finalize。

## 验收标准

- [x] `LiveRecordingCore._start_recording`（或 `create_session`）在配置 `effective_pipeline_mode()==legacy` 时拒绝**新** session（清晰错误 / 日志）
- [x] `snapshot_pipeline_mode()` 在 legacy 配置下仍可为存量场次服务
- [x] `doctor --json` 对 legacy 配置继续警告
- [x] 新增 `test_legacy_new_session_rejected`
- [x] 收窄 `test_live_legacy_pipeline.py`：仅测存量 finalize，不测新 session 创建

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_live_legacy_pipeline.py tests/unit/test_doctor_legacy_pipeline.py tests/unit/test_legacy_new_session_rejected.py -v
ruff check src/media2text/core/live/recording.py src/media2text/core/doctor_checks.py
```

## 非目标范围

- 删除 `finalize_recording_legacy` 实现（P3 / MLS-8 之后）
