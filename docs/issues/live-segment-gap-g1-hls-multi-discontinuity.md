---
issue: 281
epic: live-segment-media-gap-fix
github: 281
branch: issue-281-live-segment-gap-g1
depends_on: [274]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Gap G1：HLS 多次重连 DISCONTINUITY（D13）

## 背景

Epic `live-segment-media`（#269–#274）已交付 HLS 录制与 LW-03 重连骨架，但 **spec §6.1 / D13** 要求每次 ffmpeg 重连向 `master.m3u8` 追加 `#EXT-X-DISCONTINUITY`，且 `part_index` 单调递增。

**现网 gap（2026-06-09 代码审查）：**

- `append_discontinuity_to_playlist()` 在 playlist 已含 **任意** `#EXT-X-DISCONTINUITY` 时直接 `return`，第二次及以后重连不再追加 marker。
- 单测 `test_append_discontinuity_idempotent` 将上述行为当作正确「幂等」，与 spec 冲突。
- 多次断流重连后播放器 seek 可能跳变（spec Failure modes：「HLS 重连无 DISCONTINUITY」）。

**参考**

- [design spec §6.1、D13](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- 实现：`src/media2text/core/live/hls_recorder.py`、`recording.py` `_reconnect_segment` HLS 分支

**依赖**：#274（LSM-5）已合并。

## 验收标准

### Task 1 — 每次重连追加 DISCONTINUITY

- [x] `append_discontinuity_to_playlist`（或重命名后的 helper）：**每次** `rotate_hls_after_reconnect` 调用在 playlist 末尾追加一条 `#EXT-X-DISCONTINUITY`（允许多条；禁止「已有 marker 则跳过」）
- [x] `rotate_hls_after_reconnect` 在写入 marker 后仍由 `recording._spawn_hls_recording` 以递增 `part_index` + `discontinuity_seq` 启动新 ffmpeg（行为保持）

### Task 2 — 单测

- [x] 更新 `tests/unit/test_hls_recorder.py`：两次调用 `append_discontinuity_to_playlist` → playlist 含 **2** 条 `#EXT-X-DISCONTINUITY`
- [x] `test_hls_reconnect_appends_discontinuity_and_new_index` 仍通过；可选增加「模拟两次 rotate」集成断言
- [x] 回归：`pytest tests/unit/test_hls_recorder.py -v`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_hls_recorder.py -v
ruff check src/media2text/core/live/hls_recorder.py
```

## 非目标范围

- `duration_sec` / `discontinuity_at[]` 导出与 Desktop S4 对齐（见 G2 Issue）
- 重连失败自动降级 `flv_legacy`（spec §6.1 备选 3B，另开单）
- 修改 SegmentWatcher / 段上传逻辑

## 依赖与顺序

- **依赖**：#274
- **建议分支**：`issue-281-live-segment-gap-g1`

## GitHub

- Issue: [#281](https://github.com/oychao1988/media2text/issues/281)
