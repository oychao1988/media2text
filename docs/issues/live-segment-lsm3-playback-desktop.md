---
issue: 272
epic: live-segment-media
github: 272
branch: issue-272-live-segment-lsm3
depends_on: [270]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-3：Playback API + Desktop hls.js

## 背景

HLS 会话（#270）需无缝回放（**D10**、**S4**）：API 提供 event playlist 与 part 代理；Desktop 对 `media_format=hls` 用 **hls.js**，legacy FLV 仍 **flv.js**。`discontinuity_at[]` 用于转写时间轴对齐。

可与 #271 **并行**（契约：#270 的 `session_dir` + manifest 字段）；云 fallback 在 part `local_deleted` 时 302 或代理云 URL。

**参考**

- [design spec §8、D10、S4](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- [plan LSM-3](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)
- Desktop 验收惯例：[m2t-desktop-agent-pane-acceptance](../superpowers/verification/2026-06-06-m2t-desktop-agent-pane-acceptance.md)

## 验收标准

### Task 3.1 — Playback API

- [x] `GET /api/sessions/{id}/playback.m3u8`：返回本地 `master.m3u8`（`Content-Type: application/vnd.apple.mpegurl`）
- [x] `GET /api/sessions/{id}/parts/{index}`：本地 part 流式返回；`local_deleted` + 云存在 → 302 或代理
- [x] m3u8 内 part URI 为 API 路径（非裸文件系统路径）
- [x] `tests/unit/test_playback_api.py` 通过

### Task 3.2 — Desktop hls.js

- [x] `ViewPlayback.tsx`：`media_format=hls` → `Hls.loadSource(playbackM3u8Url)`；否则 flv.js
- [x] `playbackTime` 与 transcript 对齐；应用 `discontinuity_at` 偏移（S4，误差目标 ≤2s）
- [x] `package.json` 增加 `hls.js`；Vitest mock Hls
- [x] 无本地 part、仅云时 UI 不崩溃（graceful error 或 cloud fallback）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_playback_api.py tests/unit/test_api_* -v -m desktop
pnpm --filter m2t-desktop test
ruff check src/media2text/api/routes/playback.py
```

## 非目标范围

- SegmentWatcher / 上传流水线（#271）
- CLI `live download`（#273）
- 跨段 merge 为单 MP4（#273 `--merge`）
- 修改 Agent Pane / 左栏布局
- 非 Tauri 的 Web 独立部署

## 依赖与顺序

- **依赖**：#270（目录与 `media_format` 字段）；与 #271 可并行
- **Epic MVP**：#269–#272 合并后可验收 S1/S3/S4/S5（S2 需 #271）
- **建议分支**：`issue-272-live-segment-lsm3`

## GitHub

- Issue: [#272](https://github.com/oychao1988/media2text/issues/272)
