---
issue: 284
epic: live-segment-media-gap-fix
github: 284
branch: issue-284-live-segment-gap-g4
depends_on: [274]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Gap G4：云盘 init.mp4 + 每段 manifest 刷新（D16 补全）

## 背景

HLS fMP4 播放依赖 `init.mp4`（`#EXT-X-MAP`）。Spec **D16** 要求每 part `uploaded` 后重传 `master.m3u8`；Eng Review **ER-D6** 备选 6A 亦提到同步刷新物化 manifest。

**现网 gap：**

- `upload_live_part()` 上传 `.m4s` + `master.m3u8`；**不上传** `init.mp4`。
- 段 `delete_local_after_upload` 仅删 `.m4s`；`init.mp4` 留本地。当本地 part 已删、仅靠 **云 fallback** 播放时，客户端可能缺 init 段而无法解码。
- `session.manifest.json` 仅在 finalize `export_json` 写本地 + finalize sidecar 上传一次；**不在**每段上传后重传云盘（D16 对 manifest 的「持续增长」覆盖不完整）。

**参考**

- [design spec §4、§6.3、D6/D16](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- `src/media2text/core/cloud/live_upload.py`、`api/routes/playback.py`（init 走 `/api/media` 本地代理）

**依赖**：#274

## 验收标准

### Task 1 — 上传 `init.mp4`

- [x] `upload_live_part`（或共享 helper）：若 `session_dir/init.mp4` 存在，与 part 同次上传至云 session 根目录（`file_kind` 如 `init_mp4`）；`cloud_uploads` 记录可复用 `part_index=NULL`
- [x] 幂等：重复上传同名 init 走现有 `check_name_mode` overwrite/rename 逻辑

### Task 2 — 每段重传 `session.manifest.json`（D16）

- [x] 每 part 上传成功后调用 `SegmentManifestRepo.export_json(session_id, session_dir=...)` 物化 JSON，并上传至云 session 目录（小文件，与 m3u8 同批）
- [x] finalize sidecar 上传仍保留（不重复删 transcript）

### Task 3 — 云-only 播放

- [x] `tests/unit/test_segment_process.py` 或 `test_live_upload_hls.py`：mock client 断言 init + manifest 在上传 part 时被调用
- [x] `tests/unit/test_playback_api.py`：本地无 `init.mp4`、云有记录时，m3u8 rewrite 的 init URI 可 302/代理（若 API 需扩展则一并实现）

### Task 4 — 删本地边界

- [x] 确认 `delete_local_after_upload` **不**删除 `init.mp4`、`master.m3u8`、transcript sidecar（维持现状；文档注释一句即可）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev,desktop]"
pytest tests/unit/test_segment_process.py tests/unit/test_playback_api.py -v
ruff check src/media2text/core/cloud/live_upload.py src/media2text/core/live/segment_process.py
```

## 非目标范围

- 云端 merge 单 MP4（D6 明确不做）
- playback API 30s list 缓存（Perf3，另开单）
- 修改 SegmentWatcher 闭合逻辑

## 依赖与顺序

- **依赖**：#274
- **建议分支**：`issue-284-live-segment-gap-g4`

## GitHub

- Issue: [#284](https://github.com/oychao1988/media2text/issues/284)
