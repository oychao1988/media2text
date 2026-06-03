# Live Streaming STT Pipeline — 实时转写为主路径

**日期:** 2026-06-03  
**状态:** 已批准（PoC 已验证；eng review 2026-06-03）  
**前置:** [live-pipeline-v2-design](./2026-06-03-live-pipeline-v2-design.md)（v2 明确「录播中实时转写」为非目标；本文档为 **v3 增量**）  
**PoC:** `scripts/test_douyin_live_deepgram_stream.py`（抖音拉流 → Deepgram WS → 实时出字，已跑通）

---

## 0. 已锁定决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 默认模式 | **代码默认 `legacy`**；`config.example.yaml` 推荐 **`streaming`** | 未配 `DEEPGRAM_API_KEY` 时不行为突变；新装按 example 启用 |
| STT 引擎 | **Deepgram `listen.v1` WebSocket**（`nova-3`，`language=zh`） | PoC 已验证；与现有 REST Deepgram 配置复用 API key |
| 音频路径 | **第二路 ffmpeg** 从同一 `stream_url` 抽 mono 16kHz PCM | 不从 growing FLV 读；与录制 ffmpeg 解耦 |
| 收尾媒体 | **保留 FLV，默认不 remux MP4** | remux 仅 copy，仍占 finalize 时间与磁盘 IO；FLV 足够云备份 |
| 后处理 | **跳过 transcribe**；**summarize ∥ upload 并行**（见 §4.4） | 两者互不依赖主路径；缩短下播→云盘/摘要总延迟 |
| 开播语义 **D2** | **record + STT 均成功才 `live_started`**；任一路失败 → `live_start_failed` | 与 v2 一致；避免「在录但无字幕」静默失败 |
| 断流 P0 **D1** | **单段 streaming**；ffmpeg 重连时 **降级 legacy finalize**（remux+REST）或标记 degraded | P0 不做 transcript offset merge；避免 transcript 短于 FLV |
| DB 列 **D4** | **保留 `post_process_jobs.mp4_path` 列名**；存 FLV/MP4 路径；代码层可读作 media path | 避免 P0 做 DB 迁移 |
| enter 调用 | **仅在 `_start_recording` / 重连 resolve**；poll 不打开 Playwright | enter ~8s；不得拖 G1/G5 |
| 回退 | **`pipeline_mode: legacy`** 保持 v2 行为不变 | 流式失败或未装 deepgram-sdk 时可降级 |
| 平台范围 P0 | **抖音 only**（含 `webcast/room/web/enter` resolve） | PoC 在此路径；B 站 P1 |

未选方案（备查）：

- **单 ffmpeg tee 音视频分流** — 命令复杂、断流重连难对齐，defer  
- **Flux v2 WS** — 英文向；中文直播用 nova-3 v1 即可  
- **录 growing FLV + 周期性 REST** — 延迟高、实现丑  

---

## 1. 问题陈述

v2 将转写放在 **post_process**（录完 MP4 后 REST/Whisper），导致：

1. **下播 → 可用文字** 延迟 = remux + 队列等待 + 整段 transcribe（分钟级）  
2. **finalize 阻塞 remux**，拉长 `recording_completed`（G4）  
3. **重复解码**：录制已拉完整路流，收尾再抽音频转写  

PoC 证明：**并行 PCM → Deepgram WS** 可在直播进行中产出 `[final]` 行，下播时 transcript 基本就绪。

用户期望默认路径：

```
录制 FLV ∥ 流式 STT → 下播封存 transcript → summarize → 上传 FLV + sidecar
（无 MP4 remux，无录后 transcribe）
```

---

## 2. 目标（Success Criteria）

| ID | 指标 | 目标值 | 验收 |
|----|------|--------|------|
| S1 | 下播 → transcript 封存 | ≤ **10s**（停 ffmpeg + WS + flush） | `live timeline` `streaming_stt` stage |
| S2 | 下播 → `recording_completed` | ≤ **50s**（45s offline confirm + 停录，**无 remux**） | 对比 v2 G4，P95 应下降 |
| S3 | 下播 → `summarize_completed` | 不劣于 v2（省 transcribe 后应更快） | 通知时序 |
| S4 | 断流重连 | **P0：** 重连触发 legacy 降级或 degraded；**P1：** offset merge | 单元 + 集成测试 |
| S5 | 回退 | `legacy` 与现网行为 bit-identical | 回归测试 |
| S6 | 成本可见 | 配置/doc 注明 Deepgram 流式计费 | README |

**代理指标：** 「首条 final 字幕延迟」从开播计，P95 ≤ 30s（网络 + Deepgram 冷启动）。

---

## 3. 非目标（v3 P0 不做）

- B 站 streaming STT（P1）  
- 直播中 push 通知 partial 字幕（仅 debug log / 可选 `notify.events.transcribe_partial` P2）  
- 替换 VOD / 作品 transcribe 路径  
- 去掉 `legacy` 模式  
- 直播页 UI / 字幕烧录  

---

## 4. 架构

### 4.1 进程模型（streaming 模式）

```
                    stream_url (resolve 一次，重连可刷新)
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   ffmpeg copy            ffmpeg PCM          (可选) 心跳
   → {stamp}.flv          → Deepgram WS
         │                    │
         │                    ├─ interim (内存)
         │                    └─ final → TranscriptWriter
         │                              │
         │                              ▼
         │                    {stamp}.transcript.partial.json
         │                    (periodic flush, 默认 30s)
         │
         └─ reconnect → {stamp}_rN.flv  (现有逻辑)
```

**LiveTick 内（与 v2 相同线程）：**

- `start_recording`：启动 **RecordingHandle** = `{ record_proc, stt_session }`  
- `poll_active`：两路进程存活检测；任一路异常按策略重连或 finalize  
- `_finalize_recording`（streaming）：停两路 → **不 remux** → `local_path=*.flv` → 封存 transcript → enqueue post_process  

**禁止：** 在 LiveTick 内阻塞 summarize / upload / Deepgram 网络 IO（除 stop 时短 flush）。

### 4.2 时序（streaming vs legacy）

```
streaming 模式 — 下播后
──────────────────────────────────────────────────────────►

[offline 确认] stop record_proc + stt_session
    ├─ finalize transcript (.partial → .transcript.json/.md)
    ├─ event: streaming_stt (completed)
    ├─ event: remux (skipped)  或 无 remux stage
    ├─ notify: recording_completed  (FLV path)
    ├─ notify: transcribe_completed (可选合并，见 §7)
    └─ enqueue post_process (summarize ∥ upload)

legacy 模式 — transcribe 仍串行在前；summarize ∥ upload 同 streaming（§4.4）
```

### 4.3 模块边界

| 模块 | 职责 |
|------|------|
| `core/live/streaming_stt.py` | `StreamingSttSession`：spawn PCM ffmpeg、Deepgram WS 线程、增量 writer |
| `core/live/transcript_writer.py` | 统一 partial/final 落盘格式（与 `write_transcript_outputs` 兼容） |
| `core/platform/douyin/live_enter.py` | `resolve_stream_via_web_enter()` — 从 PoC 提升 |
| `LiveRecordingCore` | 分支 `pipeline_mode`；进程字典扩展 |
| `post_process.py` | skip transcribe；**summarize ∥ upload** fan-out |
| `live_upload.py` | `local_path` 泛化；FLV + sidecar；可选 **summary 补传** |

### 4.4 post_process：summarize 与 upload 并行

**现状（v2）：** `run_post_process_job` 顺序为 transcribe → summarize → upload。upload 常等 summarize 结束，总延迟 ≈ 两者之和。

**v3 改法：** transcribe 阶段不变（streaming 下 **skip**）。transcribe 完成或跳过后，**fan-out 两路 worker**（同 job、同 DB connection 边界仍按 v2 D2：不得改 recording 列）：

```
transcribe (skip | legacy REST)
         │
         ├──────────────────┬──────────────────┐
         ▼                  ▼                  │
   summarize          cloud_upload             │
   (读 .transcript)   (FLV/MP4 + sidecar)     │
         │                  │                  │
         └──────── join ────┘                  │
                    │                          │
         summary 晚于 upload 完成？            │
                    └─► supplemental upload     │
                        (仅 .summary.*)       │
```

| 路径 | upload 首批文件 | summary 处理 |
|------|----------------|--------------|
| **streaming** | `{stamp}.flv` + `.transcript.{json,md}`（finalize 已封存） | summarize 并行；若 upload 先结束且 `upload_transcripts`，**补传** `.summary.*` |
| **legacy** | 同左（MP4 + transcript，transcribe 刚写完） | 同上 |

**实现要点：**

- 使用 `ThreadPoolExecutor(max_workers=2)` 或等价 join；**禁止**在 LiveTick 内执行。
- `live_pipeline_events`：summarize / cloud_upload 的 `started_at` 可重叠；`duration_ms` 各自统计。
- `notify.summarize_completed` / `upload_*` 仍在各自分支完成后发送（顺序不保证）。
- 单元测试：mock 慢 summarize + 快 upload，断言 upload 不等待 summarize 才开始（事件时间戳或 call order）。

---

## 5. 数据与文件布局

```
creators/{sec_uid}/live/
  20260603T123533Z.flv              # local_path（streaming）
  20260603T123533Z.transcript.json   # 封存后（与现格式一致）
  20260603T123533Z.transcript.md
  20260603T123533Z.transcript.partial.json  # 录制中（可选保留或删除）
  20260603T123533Z.summary.md         # post_process summarize
```

**`live_sessions` 新增/复用：**

| 列 | 说明 |
|----|------|
| `pipeline_mode` | `streaming` \| `legacy`（session 创建时快照） |
| `transcribe_status` | 录制中可设 `streaming`；finalize 后 `completed` / `failed` |
| `local_path` | `.flv` 或 `.mp4` |

**`live_pipeline_events` 新增 stage：**

| stage | status |
|-------|--------|
| `streaming_stt` | started / completed / failed / skipped |
| `remux` | streaming 下 `skipped` |

**`post_process_jobs`：** 列名仍为 **`mp4_path`**（**D4**）；值为 `.flv` 或 `.mp4` 绝对路径。Repo 层可加 `media_path` property 别名，P1 再考虑 rename 迁移。

---

## 6. 断流重连与 transcript 合并

现有录制：`{stamp}_r1.flv`, `_r2.flv` … legacy finalize 时 concat → mp4。

### P0（**D1 已锁定**）：单段或降级

| 场景 | 动作 |
|------|------|
| **无重连** | 与 PoC 相同：单 FLV + 单 WS transcript |
| **ffmpeg 重连**（出现 `_r1.flv`） | **不**在 streaming 下做 merge；session 标记 `streaming_stt=degraded`，finalize 走 **legacy**（concat/remux + post_process REST transcribe），或整段 session 创建时即 `pipeline_mode=legacy` |
| **STT 断、录制续** | STT 侧重连（`streaming_stt.reconnect`）；仍失败 → 同上降级 |

### P1：offset merge（原设计保留）

```
segment 0: t0=0,     ffmpeg+STT run #1
reconnect: stop STT #1, save segment transcript
segment 1: t0=offset_end_0, new WS
finalize:  merge FLV (optional) + TranscriptWriter.merge(segments)
```

---

## 7. 配置

```yaml
live:
  pipeline_mode: streaming          # streaming | legacy
  remux_on_complete: false          # streaming 默认 false；legacy 默认 true
  transcribe_on_complete: false     # streaming 必须 false（由流式替代）

  streaming_stt:
    enabled: true                   # pipeline_mode=streaming 时生效
    engine: deepgram
    flush_interval_sec: 30
    reconnect: true                 # STT 侧重连（独立于 ffmpeg 重连）

transcribe:
  deepgram:
    model: nova-3
    # REST 字段仍用于 legacy；streaming 复用 model/language/api_key_env
```

**默认策略（D3）：**

- **`config.example.yaml`：** `pipeline_mode: streaming`  
- **代码缺省：** `legacy`  
- **`doctor`：** 若 example 为 streaming 但未配 Deepgram key，提示降级或补 key

---

## 8. 通知

| kind | streaming 行为 |
|------|----------------|
| `live_started` | **record + STT 均成功**（D2） |
| `live_start_failed` | 任一路启动失败 |
| `recording_completed` | FLV 就绪 + transcript 封存 |
| `transcribe_completed` | finalize 时若 transcript ok **立即发**（与 recording 间隔 ≤5s）；不再等 post_process |
| `summarize_completed` | 不变 |
| `upload_*` | 不变；路径改为 FLV 文件名 |

---

## 9. 抖音 stream resolve（P0 必做）

| 路径 | 方法 |
|------|------|
| reflow API（现有） | `get_room_reflow` — 对 web room id 常失败 |
| **web enter（新增）** | Playwright 打开 `live.douyin.com/{web_room_id}`，拦截 `webcast/room/web/enter` |

`resolve_stream_url` 顺序：**enter（若 session 可用）→ reflow fallback**。

---

## 10. 实现分期

| 阶段 | 内容 | 文件约数 |
|------|------|----------|
| **P0** | `streaming_stt` + `LiveRecordingCore` 分支；D1 重连降级；post_process 并行；抖音 enter resolve | ~9 |
| **P1** | 断流 transcript offset merge + FLV concat 可选；B 站 | +6 |
| **P2** | partial 通知；metrics；`live stats` streaming 列 | +4 |

---

## 11. 测试策略（摘要）

- 单元：`TranscriptWriter` merge/flush；enter payload 解析（fixture JSON）  
- 单元：`finalize` streaming 不调用 remux（mock ffmpeg）  
- 集成：mock Deepgram WS server + fake PCM pipe  
- 回归：`pipeline_mode=legacy` 全量现有 live tests 不变  
- **并行：** `test_post_process_summarize_upload_parallel` — upload 不阻塞于 summarize  

---

## 12. 风险

| 风险 | 缓解 |
|------|------|
| Deepgram WS 断 | STT 重连 + `transcribe_status=failed` 时可选 legacy 补跑 REST |
| 双 ffmpeg CPU/带宽 | 音频路极低负载；可配置 `streaming_stt.enabled: false` 仅录 |
| FLV 兼容性 | 云盘/本地播放器说明；可选 `remux_on_complete: true` |
| 成本 | 文档 + config 注释；`doctor` 提示 streaming 模式 |

---

## Eng review 决策记录（2026-06-03）

| ID | 决策 | 选择 |
|----|------|------|
| D1 | P0 断流 | 单段 streaming；重连 → legacy finalize 或 degraded |
| D2 | STT 失败 | 两路均成功才 `live_started` |
| D3 | 默认模式 | 代码 `legacy`；example `streaming` |
| D4 | DB 列 | 保留 `mp4_path` |
| D5 | post_process | **summarize ∥ upload**（用户追加，§4.4） |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | 未跑 |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | **clean** | D1–D5 已锁定；12 test gaps 列入 P0 计划 |
| Design Review | `/plan-design-review` | UI/UX | 0 | — | 无 UI |
| DX Review | `/plan-devex-review` | CLI/DX | 0 | — | 未跑 |

**UNRESOLVED:** 0  
**VERDICT:** **ENG CLEARED** — 可开 P0 实现

