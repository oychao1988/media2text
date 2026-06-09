---
issue: 270
epic: live-segment-media
github: 270
branch: issue-270-live-segment-lsm1
depends_on: [269]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-1：HLS 录制 + DB + LW-03 重连

## 背景

在 PoC（#269）门禁后，将 streaming 直播录制从单文件 FLV 切换为 **HLS fMP4 分段**（`live/{anchor}/master.m3u8` + `parts/seg-*.m4s`），同时：

- `live_session_parts` / `segment_process_jobs` 为权威状态（**D14**）
- LW-03 重连走 HLS **DISCONTINUITY + 单调 part index**（**D13**），不 concat FLV
- **GF-5** 回归：STT 并行、`finalize` ≤10s 不 await 上传

本 Issue 对应 **LSM-1**；不实现段级上传（LSM-2）与播放 API（LSM-3）。

**参考**

- [design spec §4–§6、D11–D16](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- [plan LSM-1](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)

**依赖**：#269（PoC 表可读；压缩默认开关按验收表）

## 验收标准

### Task 1.1 — Schema + SegmentManifestRepo

- [x] 迁移：`live_session_parts`、`segment_process_jobs`；`cloud_uploads.part_index` nullable
- [x] `SegmentManifestRepo`：`upsert_part`、`mark_closed`、`mark_uploaded`、`mark_local_deleted`、`list_parts`、`export_json`
- [x] `tests/unit/test_segment_manifest.py`：part 状态机 `recording → closed` 通过

### Task 1.2 — `hls_recorder.py`

- [x] `build_hls_recorder_args` / `spawn_hls_recorder`：输出 `session_dir/master.m3u8` + `parts/seg-%05d.m4s`
- [x] `stop_hls_recorder` 优雅停止；finalize 写 ENDLIST（或等价 hls flags）
- [x] `tests/unit/test_hls_recorder.py` 通过

### Task 1.3 — LW-03 HLS 重连（D13）

- [x] `rotate_hls_after_reconnect`：master 追加 `#EXT-X-DISCONTINUITY`，DB `discontinuity_seq` + export `discontinuity_at[]`
- [x] `recording.py`：`live.media.format=hls` 时重连走 HLS 分支，**不** FLV concat
- [x] 单测：`EXT-X-DISCONTINUITY` 与新 part index 递增

### Task 1.4 — Config + 主路径

- [x] `config.py` + `config.example.yaml`：`live.media.*`、`live.compress.*`、`live.segment_pipeline.*`（spec §9）
- [x] `pipeline_mode=streaming` + `media.format=hls` → LW-01 用 `hls_recorder`；`format=flv` / `flv_legacy` 保持现网
- [x] 会话目录 `live/{anchor}/`；`live_sessions.session_dir` 持久化
- [x] **回归**：`streaming_stt` 仍并行；`pytest tests/unit/test_streaming_stt*.py` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev,transcribe-deepgram]"
pytest tests/unit/test_segment_manifest.py tests/unit/test_hls_recorder.py tests/unit/test_live_recording*.py tests/unit/test_streaming_stt*.py -v
ruff check src/media2text/core/live/hls_recorder.py src/media2text/core/live/recording.py src/media2text/core/storage/
```

## 非目标范围

- SegmentWatcher、`segment_process` pool、段级 aliyun 上传（#271）
- Scheduler `segment_process` 顺序调整（#271）
- Playback API / Desktop hls.js（#272）
- 删除 legacy FLV 录制路径
- `live download` CLI

## 依赖与顺序

- **依赖**：#269（压缩默认策略）
- **阻塞**：#271、#272（需本单 schema + 目录布局）
- **建议分支**：`issue-270-live-segment-lsm1`

## GitHub

- Issue: [#270](https://github.com/oychao1988/media2text/issues/270)
