---
issue: 327
epic: live-recording-stability-2026-06-17
github: 327
branch: issue-327-lr3-hls-stall-reconnect
depends_on: [326]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
---

# LR-3：HLS 长分片 stall 误判与重连风暴

## 背景

2026-06-17 戈锐直播 session `aabf6a42`：`pipeline_mode=streaming`、`live.media.format=hls`、`segment_duration_sec=600`。

- 10 分钟分片期间 m3u8/seg 文件长时间不增长 → `_maybe_recover_stalled_hls` 在 **45s grace + 3 次 poll** 后触发 `hls_only` 重连
- 与 `_maybe_recover_stalled_stream`（transcript 90s stall → `full` 重连）**同 tick 可叠加**，63s 内 3 次重连
- 重连后 `init.mp4` 0 字节、`master.m3u8` 卡在 `seg-00002`，僵尸 ffmpeg，播放缺口 ~6 分钟

**参考**：`src/media2text/core/live/recording.py`（`TRANSCRIPT_STALL_RECONNECT_SEC`、`HLS_STALL_*`、`_maybe_recover_stalled_*`）

## 复现步骤

1. 配置 HLS + `segment_duration_sec: 600`，对长直播开录。
2. 等待当前分片写入完成、下一分片尚未闭合（正常 10min 间隔）。
3. 观察日志：`live_hls_stall_reconnect` 与 `live_stream_stall_reconnect` 短时间连续触发，`reconnect_attempts` 快速递增。

## 验收标准

### Task 1 — HLS stall 阈值与分片时长对齐

- [x] HLS stall grace / poll 阈值考虑 `segment_duration_sec`：长分片下不在「分片间歇期」误判 stall（例如 grace ≥ min(segment_duration * 0.1, 120s) 或可配置）
- [x] `_hls_recording_healthy`：分片文件 mtime 在分片周期内未变但 ffmpeg log 仍增长时视为健康

### Task 2 — 重连互斥与冷却

- [x] 同一 session 在 `_stall_recovery_inflight` 或最近一次重连后 **冷却窗口**（如 120s）内不重复触发 transcript-stall 与 hls-stall 两条路径
- [x] 若 transcript-stall 已触发 `full` reconnect，同 tick 跳过 `hls_only` reconnect

### Task 3 — 重连后 init 完整性

- [x] `_reconnect_hls_ffmpeg_only` / `_spawn_hls_recording`：新 ffmpeg 启动后校验 `init.mp4` 非空；若 0 字节则从 `init-{n}.mp4` 回退复制（与 rotate 逻辑一致）

### Task 4 — 单测

- [x] 新增/更新 `tests/unit/test_hls_recorder.py` 或 `test_recording_stall.py`：长分片配置下不应在 grace 内触发 hls stall；互斥与冷却断言

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_hls_recorder.py tests/unit/test_recording_stall.py -v --tb=short
ruff check src/media2text/core/live/recording.py
```

## 非目标范围

- 降级 `flv_legacy` 自动切换（spec 3B，另开单）
- STT 与视频 startup offset 补偿（#101 范畴）
- 云盘 segment 上传逻辑
- 修改默认 `segment_duration_sec` 配置

## 依赖与顺序

- **依赖**：#326
- **建议分支**：`issue-327-lr3-hls-stall-reconnect`

## GitHub

- Issue: [#327](https://github.com/oychao1988/media2text/issues/327)
