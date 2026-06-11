---
issue: 296
epic: session-media-unified
github: 296
branch: issue-296-smu-r2-playback-unify
depends_on: [272, 284]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R2：播放统一（Range 代理 + 云 master + Desktop hls.js）

## 背景

Session Media Unified Refactor 的 **MVP 闸门**。Dogfood 场次 `20260611T110019Z`：`media_format=hls`、多段已上传、`discontinuity_at=[630.76]`、本地 `.m4s` 部分删除；Desktop 因 `hlsNeedsRemux` 走 `playback.mp4` remux 失败。

**目标（spec U4/U9/U10、US4/US9/US10）：**

- Part/init 云回退：**API Range 流式代理**，替代 Aliyun 302（~15min TTL 导致 hls.js 断播）
- `playback.m3u8`：本地 `master.m3u8` 缺失时读云 master 并重写 URI
- Desktop：**始终** `playbackM3u8Url` + hls.js（含 discontinuity）；云-only 失败时增强 error copy

**参考**

- [design spec §4.2–4.3、US4/US9/US10](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [implementation plan SMU-R2 + Desktop UX](../superpowers/plans/2026-06-11-session-media-unified.md)
- 前置：#272（LSM-3 playback API）、#284（G4 init/manifest）

## 验收标准

### Task 2.1 — `cloud_byte_proxy`

- [x] 新增 `src/media2text/api/services/cloud_byte_proxy.py`：`stream_cloud_file()` 透传 client `Range` → httpx → `StreamingResponse`（200/206）
- [x] `tests/unit/test_cloud_byte_proxy.py` 覆盖 Range 头转发

### Task 2.2 — `session_playback` 查找

- [x] 新增 `src/media2text/api/services/session_playback.py`：`find_part_upload` / `find_init_upload` / `find_m3u8_upload`（基于 `CloudUploadRepo.list_for_session`）
- [x] `tests/unit/test_session_playback.py` 通过

### Task 2.3 — Part/init Range 代理

- [x] `GET /api/sessions/{id}/parts/{index}`：本地 miss + 云 upload → `stream_cloud_file`（非 302）
- [x] `GET /api/sessions/{id}/init.mp4`：同上
- [x] 更新 `tests/unit/test_playback_api.py`（原 302 断言改为 206 代理）
- [x] **US10**：多 part 场景下 part1/part2 均返回 206 代理（非 302）；`Range: bytes=0-` 跨段 seek 不依赖 Aliyun 临时 URL

### Task 2.4 — 云 master 回退

- [x] `GET /api/sessions/{id}/playback.m3u8`：本地无 `master.m3u8` 时从云拉取 raw m3u8 → `_rewrite_m3u8`
- [x] `test_playback_m3u8_from_cloud_when_local_master_missing` 通过

### Task 2.5 — Desktop 去 remux + 云 error copy

- [x] 删除 `ViewPlayback.tsx` 中 `hlsNeedsRemux`；`discontinuity_at` 非空仍走 hls.js
- [x] 更新 `ViewPlayback.test.tsx`：discontinuity 用 `playbackM3u8Url` 而非 `playbackMp4Url`
- [x] 云-only + fetch/hls fatal：`回放加载失败` +「云端分段不可用，可尝试从云端下载」
- [x] Vitest 覆盖 cloud-only error hint

### Task 2.6 — Dogfood 手工验收（US4/US9/US10）

- [ ] 场次 `20260611T110019Z`（`discontinuity_at` 非空、本地 `.m4s` 部分缺失、云有备份）：Desktop 走 `playbackM3u8Url` + hls.js **可播**
- [ ] 删除本地 `master.m3u8` 后 `GET /api/sessions/{id}/playback.m3u8` 仍 200（云 master 回退）
- [ ] 验收记录写入 PR 描述或 `docs/superpowers/verification/` 片段（session id + 截图/日志一行即可）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_cloud_byte_proxy.py tests/unit/test_session_playback.py tests/unit/test_playback_api.py tests/unit/test_streaming_stt_finalize*.py -v -m desktop
pnpm --filter m2t-desktop test -- ViewPlayback.test.tsx
ruff check src/media2text/api/services/cloud_byte_proxy.py src/media2text/api/services/session_playback.py src/media2text/api/routes/playback.py
```

## 非目标范围

- `live.encode` 配置块（SMU-R1 / #298）
- VOD `/api/media` 云回退（SMU-R3 / #299）
- Legacy pipeline 退场日志（SMU-R4 / #300）
- 删除 `_cloud_part_redirect` 死代码（SMU-R5 / #301，本 PR 可保留一 release）
- 直播预览 `stream/proxy` 行为变更
- 新播放器 UI / timeline discontinuity 标记

## 依赖与顺序

- **依赖**：#272、#284（LSM playback + G4 已交付）
- **阻塞**：#299、#300、#301
- **可与 #297（SMU-R0）并行**（无文件冲突）
- **建议分支**：`issue-296-smu-r2-playback-unify`

## GitHub

- Issue: [#296](https://github.com/oychao1988/media2text/issues/296)
