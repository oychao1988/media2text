## 背景

Spec §3、§10 将以下能力列为 **P2**：直播中 partial 字幕通知、S1–S3 类延迟 metrics、`live stats` streaming 列展示。

P0 仅 debug log partial；S1/S2 未自动化验收。

**Spec:** [2026-06-03-live-streaming-stt-design.md](../specs/2026-06-03-live-streaming-stt-design.md) §2、§3、§10

**GitHub:** #104 · **Depends on:** #97 合并（建议 P1 offset merge 稳定后再做 metrics 语义）

## 目标

### 通知

- 可选 `notify.events.transcribe_partial`（默认 false）
- 节流策略（避免飞书刷屏）：例如每 N 秒或每 M 条 final 摘要

### Metrics / 验收自动化

- S1：下播 → transcript 封存 ≤10s（`streaming_stt` stage duration）
- S2：下播 → `recording_completed` ≤50s（含 offline confirm）
- 代理：开播 → 首条 final P95 ≤30s
- 导出：`live timeline` / JSON 字段或轻量 benchmark 脚本

### CLI

- `live stats`（或等价）展示 streaming 列：pipeline_mode、transcribe_status、partial segment count

## 验收

- [ ] config.example 文档化新 notify 开关
- [ ] 单元/集成：metrics 从 `live_pipeline_events` 计算正确
- [ ] README 注明 Deepgram 流式计费（S6，可与本 issue 一并文档化）

## 非目标

- 直播页 UI、字幕烧录
