---
issue: 300
epic: session-media-unified
github: 300
branch: issue-300-smu-r4-legacy-deprecation
depends_on: [296]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R4：Legacy pipeline 退场 + HLS finalize 瘦身

## 背景

Spec **U6**：新录走 `streaming+hls`；`pipeline_mode=legacy` 仅只读兼容。HLS finalize 不应再 remux 整文件 MP4 或 enqueue 整文件云上传（段级 upload 已在 LSM-2）。

**参考**

- [design spec §7 R4、U6](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [plan SMU-R4 Task 4.1](../superpowers/plans/2026-06-11-session-media-unified.md)

## 验收标准

### Task 4.1 — Deprecation 日志

- [x] `pipeline_mode=legacy` finalize 路径打 **一次** `log.warning("live_pipeline_deprecated", ...)`
- [x] `post_process` 整文件 upload 入队时同样 warning（若 HLS session 仍触发）

### Task 4.2 — HLS finalize trim

- [x] HLS streaming finalize **不**调用 `remux_hls_to_playback_mp4`（除非显式 legacy-only 只读工具路径）
- [x] 不 enqueue 整文件 `cloud_uploads` for HLS segment sessions
- [x] `tests/unit/test_post_process_hls_skip_upload.py` + `test_segment_finalize_sidecar.py` 回归通过

### Task 4.3 — 文档

- [x] `config.example.yaml` / CLAUDE.md 一句：legacy 仅兼容旧数据，新用户用 streaming+hls

### Task 4.4 — Legacy 播放回归（US6）

- [x] 已有 **legacy MP4** 或 **streaming FLV** 场次：`ViewPlayback` / `/api/media` 只读播放不退化（单测或既有 `test_api_history_media` 回归）
- [x] HLS 新路径变更 **不**破坏上述 legacy 分支（Vitest：`media_format !== 'hls'` 仍走 flv.js / native video）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_post_process_hls_skip_upload.py tests/unit/test_segment_finalize_sidecar.py tests/unit/test_live_legacy_pipeline.py tests/unit/test_api_history_media.py -v
ruff check src/media2text/core/live/recording.py src/media2text/core/live/post_process.py
```

## 非目标范围

- 删除 legacy 代码路径（只 deprecation + trim HLS 分支）
- 删除 `playback.mp4` remux API（#296 已 deprecated 使用，保留只读）
- Encode 默认开关（#298）

## 依赖与顺序

- **依赖**：#296（播放不再依赖 remux MP4）
- **建议分支**：`issue-300-smu-r4-legacy-deprecation`

## GitHub

- Issue: [#300](https://github.com/oychao1988/media2text/issues/300)
