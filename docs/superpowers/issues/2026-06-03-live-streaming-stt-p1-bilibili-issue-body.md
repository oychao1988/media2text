## 背景

Streaming STT P0（#97）仅支持抖音（含 `webcast/room/web/enter` resolve + 双路 ffmpeg）。Spec §0、§3 将 **B 站 streaming STT** 列为 P1。

**Spec:** [2026-06-03-live-streaming-stt-design.md](../specs/2026-06-03-live-streaming-stt-design.md) §10

**GitHub:** #102 · **Depends on:** #97 合并

## 目标

- `pipeline_mode=streaming` 对 `platform=bilibili` 创作者可用
- B 站 live stream URL resolve（复用或扩展 bilibili adapter）
- 与抖音共用 `StreamingSttSession` + `TranscriptWriter` + finalize 分支
- `doctor` / README 注明 B 站 streaming 前置条件

## 验收

- [ ] 单元：B 站 resolve fixture / mock adapter 启动 streaming 双路
- [ ] 集成或 `@pytest.mark.live`：真实 B 站房间（可选 CI skip）录短段 + partial/final 落盘
- [ ] legacy 模式 B 站行为不变

## 非目标

- offset merge（#101）
- 作品/VOD transcribe 路径变更
