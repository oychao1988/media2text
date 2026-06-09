---
issue: 271
epic: live-segment-media
github: 271
branch: issue-271-live-segment-lsm2
depends_on: [270]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-2：SegmentWatcher + Tier-1 段级上传

## 背景

HLS 录制（#270）产出闭合 `.m4s` 后，须 **异步** 压缩（若 PoC 未内嵌则跳过）→ 上传阿里云盘 → 确认后删本地段（**S1/S2/S5**）。实现：

- **D11** `SegmentWatcher`（mtime 稳定检测）入队 `segment_process`
- **D12** Scheduler：**segment_process 先于 post_process**（修复磁盘峰值）
- **D15** finalize 仅 **一次** 上传 transcript/summary/manifest；per-part 只传 `.m4s`
- **D16** 每 part 上传后重传 `master.m3u8`

本 Issue 为 Epic **MVP 关键路径**；与 #274 同触 `post_process.py` 时 **#274 须在本文合并后** 开分支。

**参考**

- [design spec §3、§6、D11–D16](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- [plan LSM-2](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)
- 关联 [#67](./aliyundrive-live-upload.md) 云路径规范

## 验收标准

### Task 2.1 — SegmentWatcher（D11）

- [x] `segment_watcher.py`：poll 闭合段（mtime 稳定）、跳过 growing file、`dedupe segment_process:{session_id}:{index}`
- [x] daemon 启动 watcher 线程；finalize 停表 + 末段 force close
- [x] `tests/unit/test_segment_watcher.py` 通过

### Task 2.2 — segment_process + pool

- [x] `segment_process.py` + `segment_process_pool.py`：worker 独立 `open_db`（仿 post_process）
- [x] 上传成功 → `mark_uploaded` → 删本地 part → `local_deleted`；失败保留本地、可重试
- [x] `live_upload.upload_part`：仅 `.m4s`；更新 `cloud_uploads.part_index`；上传后 **重传 master.m3u8**（D16）
- [x] `tests/unit/test_segment_process.py`：`upload` 确认后才删本地

### Task 2.3 — Scheduler 顺序（D12）— CRITICAL

- [x] `task_scheduler.tick_once`：在 `post_pool.drain_pending` **之前** `segment_pool.drain_pending`
- [x] `tests/unit/test_task_scheduler_segment_order.py`：`segment` 调用序在 `post` 之前
- [x] 回归 `tests/unit/test_task_scheduler.py`

### Task 2.4 — Finalize sidecar（D15）

- [x] `_finalize_recording_streaming`：封存 STT → ENDLIST → `export_session_manifest_json` → **单次** sidecar/manifest 上传
- [x] 移除 streaming finalize 内整文件 MP4 upload / FLV concat（D9）
- [x] post_process job 仅 enqueue summarize（若 enabled），无 live 整文件 upload 阶段
- [x] `tests/unit/test_segment_finalize_sidecar.py`（或等价）通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev,desktop]"
pytest tests/unit/test_segment_watcher.py tests/unit/test_segment_process.py tests/unit/test_task_scheduler_segment_order.py tests/unit/test_task_scheduler.py tests/unit/test_segment_finalize_sidecar.py -v
pytest tests/unit/test_streaming_stt*.py tests/unit/test_live_worker_tasks.py -v
ruff check src/media2text/core/live/segment_watcher.py src/media2text/core/live/segment_process.py src/media2text/core/live/task_scheduler.py src/media2text/core/cloud/live_upload.py
```

## 非目标范围

- Desktop / Playback API（#272）
- CLI `live download`（#273）
- post_process 全量瘦身与 agent-manifest（#274）
- 修改 aliyundrive 登录/OAuth
- B 站专属 HLS URL 适配（沿用现有 stream URL 解析）

## 依赖与顺序

- **依赖**：#270
- **阻塞**：#273、#274
- **建议分支**：`issue-271-live-segment-lsm2`

## GitHub

- Issue: [#271](https://github.com/oychao1988/media2text/issues/271)
