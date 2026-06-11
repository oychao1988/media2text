---
issue: 299
epic: session-media-unified
github: 299
branch: issue-299-smu-r3-vod-cloud-playback
depends_on: [296]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R3：VOD 云 Range 播放（`/api/media` 回退）

## 背景

Spec **U5/US5**：作品 MP4 本地删除后，若 `cloud_uploads` / manifest 有备份，Desktop 经 `/api/media?path=...` 仍可 Range seek 播放。复用 #296 的 `cloud_byte_proxy.stream_cloud_file`。

**参考**

- [design spec §5、US5](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [plan SMU-R3 Task 3.1](../superpowers/plans/2026-06-11-session-media-unified.md)
- 现有本地 Range：`src/media2text/api/routes/media.py`

## 验收标准

### Task 3.1 — API cloud fallback

- [x] `GET /api/media`：本地文件不存在时，按 workspace path 查 `cloud_uploads` / manifest → `stream_cloud_file`
- [x] 支持 `Range` 头；返回 200/206
- [x] `tests/unit/test_api_media_cloud_fallback.py` 通过

### Task 3.2 — Desktop error copy

- [x] VOD 云-only 播放失败时复用 #296 双行 error hint（可抽 shared 组件）
- [x] 现有 `mediaUrl` 路径不变；`media_available: false` + `cloud_available: true` 仍可发起请求

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_media_cloud_fallback.py tests/unit/test_api_history_media.py -v -m desktop
pnpm --filter m2t-desktop test
ruff check src/media2text/api/routes/media.py src/media2text/api/services/history_media.py
```

## 非目标范围

- VOD **上传**流水线（R3b / 另开 Epic）
- 作品转 HLS 分段
- 直播 part 代理（已在 #296）
- 新 VOD 专用端点 `/api/vod/{id}/playback`（除非 implementer 证明 media 回退不足）

## 依赖与顺序

- **依赖**：#296（`cloud_byte_proxy`  merged）
- **建议分支**：`issue-299-smu-r3-vod-cloud-playback`

## GitHub

- Issue: [#299](https://github.com/oychao1988/media2text/issues/299)
