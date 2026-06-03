## 背景

Spec §5 要求 session 创建时快照 `pipeline_mode`，录制中 `transcribe_status=streaming`；§5 亦建议 P1 考虑 `post_process_jobs.mp4_path` → `media_path` 迁移（D4 保留列名仅为 P0）。

当前 P0 运行时读全局 config，finalize 才写 `transcribe_status=completed|failed`。

**Spec:** [2026-06-03-live-streaming-stt-design.md](../specs/2026-06-03-live-streaming-stt-design.md) §5、§10

**GitHub:** #103 · **Depends on:** #97 合并

## 目标

- DB migration：`live_sessions.pipeline_mode`（`streaming`|`legacy`），create session 时写入
- 开播后 / 录制中：`transcribe_status=streaming`（streaming 模式且 STT 活跃）
- Repo：`PostProcessJobRepo.media_path` property 别名 `mp4_path`；文档说明 FLV/MP4 通用
- （可选）rename 迁移 `mp4_path` → `media_path` 若团队同意做 breaking migration

## 验收

- [ ] migration + 回归现有 live/post_process tests
- [ ] `creator show --json` / agent-manifest 可反映 pipeline_mode（若适用）
- [ ] 旧 DB 行 backfill 默认 `legacy`

## 非目标

- offset merge（#101）、B 站 streaming（#102）
