## 背景

Streaming STT P0（#97）在 ffmpeg 重连时按 **D1** 降级为 legacy finalize（concat/remux + REST 转写），不做多段字幕合并。Spec §6 P1 要求在不降级的情况下支持 offset merge。

**Spec:** [2026-06-03-live-streaming-stt-design.md](../specs/2026-06-03-live-streaming-stt-design.md) §6 P1、§10、S4

**GitHub:** #101 · **Depends on:** #97 合并

## 目标

- 重连时：停 STT #1，持久化该段 transcript（带时间 offset）
- 新段：新 Deepgram WS，`t0 = offset_end_0`
- finalize：`TranscriptWriter.merge(segments)` 合并为单一 `.transcript.json/.md`
- 可选：多段 FLV concat（与 v2 录制 `_rN` 对齐）

## 验收

- [ ] 单元：`TranscriptWriter.merge` 多段 offset 正确、无重叠/空洞策略 documented
- [ ] 集成：mock 双段 STT + 双段 FLV，streaming finalize 不触发 legacy REST
- [ ] 回归：无重连路径与 P0 行为一致

## 非目标

- B 站（#102）
- partial 飞书通知（#104）
