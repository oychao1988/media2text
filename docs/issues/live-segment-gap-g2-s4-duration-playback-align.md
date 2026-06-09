---
issue: 282
epic: live-segment-media-gap-fix
github: 282
branch: issue-282-live-segment-gap-g2
depends_on: [274]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Gap G2：part duration + S4 转写时间轴对齐

## 背景

**Success Criterion S4**：播放 seek 与转写时间轴对齐，误差 ≤ 2s。Epic #272 验收勾选「应用 `discontinuity_at`」，但实现仍为占位：

- `SegmentManifestRepo.export_json()` 的 `discontinuity_at[]` 依赖各 part 的 `duration_sec` 累加偏移。
- 生产路径（`SegmentWatcher.mark_closed` / `recording._close_hls_part_if_any`）**从未写入** `duration_sec` → manifest 中 `discontinuity_at` 恒为空。
- Desktop `alignPlaybackTime()` 对 `discontinuityAt` 为 **noop**（`void discontinuityAt; return mediaTime`）；Vitest 仅断言「连续 HLS 时间不变」。

**参考**

- [design spec S4、§6.1、D13/D14](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- `segment_manifest.py`、`segment_watcher.py`、`apps/m2t-desktop/src/features/history/playbackTime.ts`
- API：`sessions_list.py` 从 `session.manifest.json` 暴露 `discontinuity_at`

**依赖**：#274；可与 G1 并行（不同文件为主）。

## 验收标准

### Task 1 — 段闭合时写入 `duration_sec`

- [x] 段标 `closed` 时从 `master.m3u8` 解析该 part 对应 `#EXTINF` 时长（秒），写入 `live_session_parts.duration_sec`（允许 ±0.5s 解析误差）
- [x] 覆盖路径：`SegmentWatcher` 闭合、`force_close_session`、`recording._close_hls_part_if_any`
- [x] 单测：`tests/unit/test_segment_manifest.py` 或新 `test_segment_duration_parse.py` —  fixture m3u8 + 闭合后 `export_json()` 的 `discontinuity_at` 非空且与预期偏移一致

### Task 2 — `discontinuity_at` 语义修正

- [x] `export_json()`：`discontinuity_at` 在 `discontinuity_seq > 0` 的 part **起始媒体时间**（累计 prior parts `duration_sec`）处记录；与 spec §6.1「秒级偏移供 S4」一致
- [x] finalize 后 `session.manifest.json` 含可用 `discontinuity_at`；`GET /api/sessions` 列表字段同步

### Task 3 — Desktop `alignPlaybackTime`（S4）

- [x] 实现 `alignPlaybackTime(mediaTime, discontinuityAt)`：按 `discontinuity_at` 边界将 **播放器连续时间** 映射到 **转写时间轴**（重连造成的离线间隙补偿；目标误差 ≤2s）
- [x] 更新 `playbackTime.test.ts`：给定 `discontinuity_at=[120]` 与 part 时长 fixture，断言 seek 120s 后 transcript 索引偏移符合预期
- [x] `ViewPlayback.tsx` 仍通过 `onTimeUpdate(alignPlaybackTime(...))` 驱动 transcript 高亮

### Task 4 — 文档 / 验收表

- [x] 在 `docs/superpowers/verification/2026-06-09-live-segment-media-acceptance.md` 的 S4 行补充「G2 实现后」验证说明（非阻塞 epic_verify）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev,desktop]"
pytest tests/unit/test_segment_manifest.py tests/unit/test_segment_watcher.py -v
pnpm --filter m2t-desktop test -- playbackTime
ruff check src/media2text/core/live/segment_manifest.py src/media2text/core/live/segment_watcher.py
```

## 非目标范围

- 多次 DISCONTINUITY marker 写入（G1）
- 修改 Deepgram STT offset merge（#101 已覆盖 transcript 侧）
- E2E 真机 Desktop seek 手测（可人工补，不纳入 CI）

## 依赖与顺序

- **依赖**：#274
- **建议与 G1 并行**；合并前注意 `hls_recorder.py` 冲突
- **建议分支**：`issue-282-live-segment-gap-g2`

## GitHub

- Issue: [#282](https://github.com/oychao1988/media2text/issues/282)
