# Live Segment Media Pipeline — 分段录制 / 压缩 / 上传 / 播放 / 下载

**日期:** 2026-06-09  
**状态:** 已定稿（Eng Review 2026-06-09；架构 D11–D16 已采纳）  
**前置:** [Live Streaming STT v3](./2026-06-03-live-streaming-stt-design.md)、[Local Pipeline Refactor](./2026-06-08-m2t-local-pipeline-refactor-design.md)、[Aliyun Drive Live Upload](../../issues/aliyundrive-live-upload.md)  
**被依赖:** m2t-desktop 回放、CLI `live download`、Epic `live-segment-media`

---

## 0. 已锁定决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 分段容器 **HLS fMP4**（`-f hls -hls_playlist_type event`） | 工业播放标准；hls.js / Safari；seek + 连贯播 |
| D2 | **压缩默认开**；启用前须 **Phase 0 PoC 通过**（见 §8） | 用户要求默认压缩；避免未验证参数上生产 |
| D3 | 压缩时机：**录制时一次编码**（主路径）；async 段后压缩为 fallback | 避免 copy 大文件再压；磁盘峰值最小 |
| D4 | **上传默认开**；**段闭合后异步上传**；本地 **默认不保留** | 方案 C：本地 ≈ 当前段 + 在途上传 |
| D5 | **实时转写**保持 **第二路 PCM ffmpeg + Deepgram WS**；与视频分段正交 | transcript 仍为 session 级单文件 |
| D6 | 云盘 **session 目录镜像**；**不**在云端 merge 单 MP4 | 个人版 API 无服务端合并 |
| D7 | 播放：**API `master.m3u8`** + Desktop **hls.js** | 替代单 FLV + flv.js |
| D8 | **Tier 隔离**（§3）：录制/STT 不得 await 压/传；段处理 **独立 Worker 池** | 后续流程不影响录制 |
| D9 | finalize **不** concat 整场 / **不**整文件 upload | 段级 pipeline |
| D10 | `flv_legacy` 保留一版回退；默认 **streaming + hls** | 平滑迁移 |
| D11 | **SegmentWatcher**（mtime poll）检测段闭合 → 入队 Tier-1 | Tier-0 不 await 压/传 |
| D12 | Scheduler：**segment_process 先于 post_process** | 满足 S1 磁盘峰值 |
| D13 | LW-03：**新 ffmpeg + `#EXT-X-DISCONTINUITY` + 递增 seg index** | 不可照搬 FLV concat |
| D14 | **`live_session_parts` DB 为权威**；`session.manifest.json` 物化导出 | 避免双写 race |
| D15 | 段上传 **仅 `.m4s`**；transcript/summary **finalize 单次** sidecar 上传 | 与 session 级 STT 正交 |
| D16 | 每段 `uploaded` 后 **重传** `master.m3u8`（+ 物化 manifest） | EVENT playlist 持续增长 |

---

## 1. 问题陈述

**现网：**

```
ffmpeg -c copy → 单 FLV → finalize merge → 整文件 upload → delete_local
```

**痛点：** 磁盘占满、上传滞后、无压缩、单文件播放/下载、无法边录边腾盘。

**目标默认：** 实时转写开、分段开、压缩开（PoC 后）、上传开、本地段默认删、HLS 连贯播放、分段下载可 merge。

---

## 2. Success Criteria

| ID | 指标 | 目标 |
|----|------|------|
| S1 | 本地磁盘峰值 | ≤ 2 × segment_size |
| S2 | 段闭合 → 上传完成 P95 | ≤ segment_duration + 5min |
| S3 | STT | 同 v3（finalize 封存 ≤10s） |
| S4 | 播放 seek 与转写对齐 | 误差 ≤ 2s |
| S5 | 故障隔离 | upload/compress 失败不停录 |
| S6 | 压缩 PoC | 体积 ≤ 原 40%；VT ≥ 1.0× realtime |
| S7 | `live download --merge` | 可还原可播 MP4 |

---

## 3. 三层 Tier 架构

```
Tier-0 实时（Probe → Reconciler → Live Worker）
  LW-01 HLS 录制 | LW-02/04 STT | LW-03 重连 | LW-05 finalize
  禁止：await compress / upload

SegmentWatcher（daemon 线程，D11）
  mtime poll parts/*.m4s → closed → INSERT segment_process_jobs

Tier-1 段后处理（SegmentWorkerPool，独立线程池）
  [compress?] → upload part → refresh cloud m3u8 → delete_local
  dedupe: segment_process:{session_id}:{index}
  compress 跳过条件：HLS 录制已带编码（D3 主路径）；仅 copy/legacy 走 async 压

Tier-2 会话收尾（post_process）
  summarize only；无整文件 upload
```

### 故障隔离矩阵

| 失败 ↓ | 录制 | STT | 段压缩 | 段上传 |
|--------|------|-----|--------|--------|
| 压缩失败 | 继续 | 继续 | 重试/传原段 | — |
| 上传失败 | 继续 | 继续 | — | 重试 |
| STT 断线 | 继续 | reconnect | — | — |

---

## 4. 文件布局

### 本地

```
creators/{sec_uid}/live/{anchor}/
  master.m3u8
  session.manifest.json
  parts/seg-00001.m4s ...
  {anchor}.transcript.json / .md
  {anchor}.summary.md
```

### 云盘（镜像）

```
media2text/{platform}/{nickname}/live/{anchor}/
  master.m3u8
  parts/seg-*.m4s
  + sidecar
```

### part.state

`recording` → `closed` → `compressing?` → `ready` → `uploading` → `uploaded` → `local_deleted` | `failed`

---

## 5. 模块

| 模块 | 职责 |
|------|------|
| `hls_recorder.py` | spawn HLS ffmpeg；LW-03 重连旋转 |
| `segment_watcher.py` | 段闭合检测；`closed` + 入队（D11） |
| `segment_manifest.py` | DB CRUD；`export_session_manifest_json()` |
| `segment_process.py` | 单 part 压/传/删/刷新 cloud m3u8 |
| `segment_process_pool.py` | Tier-1 池（仿 `PostProcessExecutor`） |
| `api/routes/playback.py` | m3u8 + part fallback |
| `ViewPlayback.tsx` | hls.js |
| CLI `live download` | 分段拉取 + 可选 merge |

---

## 6. 任务与 DB

**Tier-0：** 沿用 `monitor_tasks` LW-*（`hls_recorder` 替换 `record_stream_copy` 主路径）

**Tier-1 新表：**

```sql
-- live_session_parts（权威，D14）
session_id, part_index, rel_path, state, bytes, duration_sec,
discontinuity_seq, cloud_path, uploaded_at, local_deleted_at, error

-- segment_process_jobs
id, session_id, part_index, status, attempts, last_error, claimed_at

-- cloud_uploads 扩展：part_index INTEGER NULL（整 session sidecar 用 NULL）
```

**索引：** `(session_id, state)` on `live_session_parts`

**Scheduler tick 顺序（D12，`task_scheduler.py`）：**

```
reconcile_live → reconcile_content
→ claim/drain live P0 (finalize)
→ drain live P1–9
→ segment_process_pool.drain_pending   # 优先腾盘
→ post_process_pool.drain_pending      # 仅 summarize
→ drain content P10+
→ notify drain_once
```

**Reconciler RR（Tier-1）：** `segment_process_jobs` failed → reset pending（上限 `max_attempts`）；`live_session_parts` stuck `uploading` → stale reset。

### 6.1 LW-03 HLS 重连（D13）

现网 `_reconnect_segment`（FLV append + finalize concat）**不适用于 HLS**。

重连步骤：

1. 停止旧 HLS ffmpeg（保留已写 `parts/` 与 `master.m3u8`）。
2. `discontinuity_seq += 1`；下一段 `part_index` 单调递增（禁止覆盖已有 `seg-*.m4s`）。
3. 向 `master.m3u8` 追加 `#EXT-X-DISCONTINUITY`（由 ffmpeg 或 `segment_manifest` 后处理写入）。
4. 启动新 ffmpeg，`hls_segment_filename` 从 `seg-{next:05d}.m4s` 继续。
5. DB `live_session_parts.discontinuity_seq` + manifest `discontinuity_at[]`（秒级偏移，供 S4）。

失败回退：连续 N 次重连失败 → 标记 session，`pipeline_mode` 可降级 `flv_legacy`（D10，仅手工/config）。

### 6.2 SegmentWatcher（D11）

- 与 `TaskSchedulerLoop` 同 daemon 进程，**独立线程**，1s poll（可配置 `segment_pipeline.watch_interval_sec`）。
- 检测：`parts/seg-*.m4s` mtime 稳定 ≥2s 且不在 `recording` 集合 → `state=closed` → `INSERT segment_process_jobs`（dedupe key）。
- 当前正在写的段（ffmpeg 仍持有）：**不**闭合（文件 size 仍在增长）。
- LW-05 finalize：Watcher 停止；末段强制闭合；`master.m3u8` 写 `#EXT-X-ENDLIST`。

### 6.3 Sidecar 与删本地（D15 / D16）

| 时机 | 上传对象 |
|------|----------|
| 每段 `uploaded` | `parts/seg-*.m4s` + **重传** `master.m3u8` |
| LW-05 finalize | `.transcript.json/.md`、`.summary.md`（若有）、物化 `session.manifest.json` |
| 删本地 | 仅当 `live_session_parts.state=uploaded` 且云路径确认；**禁止**删 transcript |

`delete_local_after_upload` 不删 session 根目录 sidecar 文件。

---

## 7. 压缩 PoC（Phase 0 门禁）

脚本：`scripts/benchmark_live_compress.py`  
验收：`docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`  
通过后 `live.compress.enabled: true` 写入 example。

默认编码（macOS）：

```bash
-c:v hevc_videotoolbox -b:v 2M -c:a aac -b:a 128k
-f hls -hls_time 600 -hls_playlist_type event
```

---

## 8. 播放与下载

**API：** `GET /api/sessions/{id}/playback.m3u8`；`GET .../parts/{index}`  
**Desktop：** hls.js；`playbackTime` 对齐 transcript  
**CLI：**

```bash
media2text live download <session_id> --parts all [--merge] [--keep-local] --json
```

`--keep-local` 默认 false。

---

## 9. 配置摘录

```yaml
live:
  pipeline_mode: streaming
  media:
    format: hls
    segment_duration_sec: 600
  compress:
    enabled: false   # PoC 后 true
    encoder: videotoolbox
    video_bitrate: 2M
  segment_pipeline:
    enabled: true
    max_parallel: 2
    upload:
      enabled: true
      delete_local_after_upload: true
```

---

## 10. Epic 顺序

| Phase | 内容 |
|-------|------|
| P0 | 压缩 PoC |
| P1 | HLS 录制 + manifest + DB |
| P2 | SegmentWorker + 段级 upload |
| P3 | Playback API + hls.js |
| P4 | `live download` |
| P5 | post_process 收尾 + 文档 |

---

## 11. 现网 vs 目标

| 项 | 现网 | 目标 |
|----|------|------|
| 录制 | 单 FLV copy | HLS 分段 + 压缩 |
| 上传 | finalize 整文件 | 段闭合异步 |
| 播放 | 单文件 flv.js | hls.js |
| 磁盘 | 整场 | ≈ 2 段 |
| STT | 第二路 PCM | 不变 |

---

## 12. Eng Review（2026-06-09）

**分支:** `main` @ `41b1b69`  
**结论:** 方向正确；架构缺口已通过 **D11–D16** 写入 §0/§6。  
**MVP:** P0–P3；P4/P5 后续 PR。  
**Implementation plan:** [2026-06-09-live-segment-media-pipeline.md](../plans/2026-06-09-live-segment-media-pipeline.md)

### Step 0 — Scope Challenge

| 检查项 | 结论 |
|--------|------|
| 现有可复用 | `record_stream_copy`、`streaming_stt.py`、`_reconnect_segment` 索引续传、`PostProcessPool` 模式、`live_upload.py` 上传/rolling_cleanup、`task_scheduler` reconcile 骨架 |
| 最小闭环 | **P0 + P1 + P2 + P3** 即可验证 S1/S2/S5；`live download` 与 summarize 改造可延后 |
| 复杂度 | 8+ 新模块 + 2 新表 → 合理，但 **不应** 同时改 `flv_legacy` 与 HLS 行为；`flv_legacy` 仅保 regress |
| 搜索 [Layer 1] | ffmpeg **内置** HLS segmenter；hls.js **标准**播放；段任务 dedupe 复用 `monitor_tasks` claim 模式 |
| 完整性 | spec 缺 Segment 闭合检测、LW-03 HLS 重连、transcript/sidecar 与删本地时序 → 需补全，非 shortcut |
| 分发 | CLI/API 随现有 `pip install` / Tauri sidecar，无新 artifact |

### What already exists

| 能力 | 现网位置 | spec 是否复用 |
|------|----------|---------------|
| FLV 录制 + 重连 concat | `ffmpeg.py`, `recording.py` | 替换为 HLS；重连语义需重写 |
| Streaming STT | `streaming_stt.py` | ✅ 保持 |
| 整文件云上传 + transcribe gate | `live_upload.py:39-53` | 段级需新 gate 规则 |
| Post-process 线程池 | `post_process_pool.py` | Tier-2 仅 summarize |
| Scheduler tick 顺序 | `task_scheduler.py:56-95` | ⚠️ 见 D2 |
| Desktop 单文件播放 | `ViewPlayback.tsx` + flv.js | 换 hls.js |
| `cloud_uploads` + rolling_cleanup | `repos.py`, `live_upload.py` | 需 per-part 行 |

### NOT in scope（本 Epic 明确不做）

| 项 | 理由 |
|----|------|
| 云端 merge 单 MP4 | D6；个人盘 API 无服务端合并 |
| 服务端转码 / CDN | 本地 ffmpeg 一次编码 |
| B 站/抖音 FLV URL 协议变更 | 仍拉同源；只改落盘格式 |
| 多机分布式 SegmentWorker | 单 daemon 进程内线程池足够 |
| NVENC/Linux 默认编码 | PoC 先 macOS VT；其他平台 follow-up |
| Agent 上下文 `compression:` 配置 | 与视频无关，勿混 |

### 架构 — 已采纳（→ §0 D11–D16）

#### ER-D1 — 段闭合如何触发 Tier-1？（→ D11）

**问题:** spec 写 `part closed → compress/upload`，但未定义 **谁** 在何时把 part 标为 `closed` 并入队 `segment_process_jobs`。

**推荐 1A:** `SegmentWatcher` 线程（inotify/mtime poll `parts/*.m4s` + `master.m3u8` 行数），在 **Live Worker 进程外**、与 `task_scheduler` 同 daemon，闭合后 `INSERT segment_process_jobs`。  
**备选 1B:** LW-01 ffmpeg 每段 `segment_wrap` 回调（需 ffmpeg 可解析 stdout，脆弱）。  
**备选 1C:** 仅 finalize 时批量处理（违背 S1/S2，否决）。

→ **已采纳 1A** → D11。

#### ER-D2 — Scheduler drain 顺序（→ D12）

**现网** `task_scheduler.py:82-87`：`post_process` **先于** content。

**spec §6** 写：`live → post_process → segment_process`，段上传排在 summarize **之后** → 磁盘峰值违背 S1。

**推荐 2A:** `reconcile → live(P0-9) → segment_process → post_process → content(P10+) → notify`  
**备选 2B:** segment_process 与 post_process **并行** drain（两池独立 limit）。

→ **已采纳 2A** → D12。

#### ER-D3 — HLS 重连 LW-03（→ D13）

**问题:** 现网 `_reconnect_segment` 追加 FLV 再 concat。HLS 需：**新 ffmpeg 实例**、递增 `seg-{N}`、`#EXT-X-DISCONTINUITY`、**禁止**跨实例复用 init segment 除非 EXT-X-MAP 一致。

**推荐 3A:** 每次重连 = 新 sub-playlist 或 master 追加 DISCONTINUITY + 新 index；`session.manifest.json` 记录 `discontinuity_at[]` 供 S4 对齐。  
**备选 3B:** 重连后降级 `flv_legacy` 单文件（D10 回退）。

→ **已采纳 3A** → §6.1。

#### ER-D4 — manifest vs DB（→ D14）

**风险:** 双源真相 → 播放/上传/删本地 race。

**推荐 4A:** **DB 为权威**；`session.manifest.json` 为 materialized export（finalize / agent-manifest 刷新时写）。  
**备选 4B:** 仅 JSON 文件（无 SQL 查询，Desktop/API 难）。

→ **已采纳 4A** → D14。

#### ER-D5 — Sidecar 与删本地（→ D15）

**现网** `_transcribe_gate_open`：若 `upload_transcripts` + 无 `.transcript.json` 则 **阻塞整文件上传**。

段级上传时 transcript **session 级**、直播中持续增长。若每段上传后删本地，finalize 前云侧可能缺 sidecar。

**推荐 5A:** 视频 part 上传 **不** 附带 sidecar；session finalize 时 **单次** 上传 transcript/summary/manifest；删本地 part 仅删 `.m4s`。  
**备选 5B:** 每段上传时带 **snapshot** sidecar（冗余、不一致风险）。

→ **已采纳 5A** → §6.3。

#### ER-D6 — master.m3u8 云刷新（→ D16）

EVENT playlist 直播中持续增长。仅上传一次则云端播放落后。

**推荐 6A:** 每次 part `uploaded` 后 **重传** `master.m3u8` + `session.manifest.json`（小文件，幂等）。  
**备选 6B:** 播放 API 只读本地 master，云仅 parts（cloud_fallback 拼 playlist）——复杂度高。

→ **已采纳 6A** → §6.3。

### 代码质量（spec 级，implementation 须覆盖）

| # | 严重度 | 发现 |
|---|--------|------|
| Q1 | P2 | §5 `compress?` fallback 与 D3「录制时一次编码」并存但未写清何时走 async 压 |
| Q2 | P2 | `cloud_uploads` 现按 `session_id` 整文件；段级需 `part_index` 列或子路径键 |
| Q3 | P3 | `post_process_jobs.mp4_path` 命名遗留；HLS 下应 `session_dir` 或 `manifest_id` |
| Q4 | P2 | RR 规则未写：part `failed` 重试、`local_deleted` 后 cloud_fallback 必填 |

### 测试 — 覆盖图（pytest + Vitest）

```
CODE PATHS
[+] hls_recorder.py
  ├── spawn_hls_ffmpeg()           [GAP] happy spawn
  ├── on_segment_closed (watcher)  [GAP] mtime/inotify 闭合
  ├── reconnect_rotate()           [GAP] DISCONTINUITY + index++
  └── stop / finalize seal         [GAP] master ENDLIST
[+] segment_process.py
  ├── compress_part (enabled)      [GAP] PoC params applied
  ├── compress_skip (disabled)     [GAP]
  ├── upload_part                  [GAP] [→E2E] mock aligo
  ├── delete_local_after_upload    [GAP] file gone, DB local_deleted
  ├── upload_fail → retry          [GAP]
  └── compress_fail → upload raw   [GAP]
[+] segment_manifest.py / repos
  ├── upsert_part (DB authoritative) [GAP]
  └── export_json                    [GAP]
[+] playback.py (API)
  ├── playback.m3u8 local          [GAP]
  ├── part fallback cloud          [GAP] [→E2E]
  └── 404 part                     [GAP]
[+] task_scheduler (order)         [GAP] **CRITICAL** segment before post_process
[+] streaming_stt.py               [★★★ REGRESSION] finalize ≤10s, STT ∥ record
[+] ViewPlayback.tsx
  ├── hls.js load                  [GAP] Vitest + mock hls
  ├── playbackTime ↔ transcript    [GAP]
  └── cloud-only session           [GAP]

USER FLOWS
[+] 直播中磁盘                      [GAP] [→E2E] 2-segment 后本地 ≤ 2×size
[+] Desktop 回放 seek               [GAP] [→E2E]
[+] live download --merge           [GAP] P4
[+] 上传失败不停录                  [GAP] [→E2E]
[+] GF-5: STT 慢不阻塞 LIVE_STARTED [★★★ REGRESSION] test_desktop_* / unit

COVERAGE: 2/28 paths (7%) | GAPS: 26 (5 E2E, 2 REGRESSION CRITICAL)
```

**须新增测试文件（implementation plan 引用）：**

- `tests/unit/test_hls_recorder.py`
- `tests/unit/test_segment_process.py`
- `tests/unit/test_segment_manifest.py`
- `tests/unit/test_playback_api.py`
- `tests/unit/test_task_scheduler_segment_order.py`（**CRITICAL**）
- `apps/m2t-desktop/src/features/history/ViewPlayback.test.tsx`（hls.js mock）
- `tests/unit/test_streaming_stt_finalize_regression.py`（已有则扩展）

### 性能

| # | 发现 | 建议 |
|---|------|------|
| Perf1 | 同场 3 路 ffmpeg：HLS encode + PCM +（fallback 段压） | PoC 测 CPU；`segment_pipeline.max_parallel` 默认 2 |
| Perf2 | EVENT m3u8 重传频率 = 段数/场 | 可接受（<100KB/次） |
| Perf3 | playback cloud_fallback N+1 查盘 | 批量 `list_parts` 缓存 30s |
| Perf4 | `live_session_parts` 无索引 | `(session_id, state)` 复合索引 |

### Failure modes（关键）

| 路径 | 生产失败 | 测试 | 处理 | 用户可见 |
|------|----------|------|------|----------|
| 段闭合检测漏段 | 磁盘满 | GAP | **critical gap** | 静默占盘 |
| 删本地后云 part 丢失 | 播放洞 | GAP | 禁止删直到 `uploaded` 确认 | 播放卡死 |
| HLS 重连无 DISCONTINUITY | 播跳变 | GAP | 3A | seek 错位 |
| post_process 先于 segment | 磁盘满 | GAP | 2A | 录播中断风险 |
| STT 阻塞 LW-05 | 无通知 | REGRESSION | GF-5 | 无 recording_completed |

### 并行化（worktree）

| Step | 模块 | Depends |
|------|------|---------|
| P0 PoC | `scripts/` | — |
| P1 HLS+DB | `core/live/`, `storage/` | P0 可选 |
| P2 SegmentWorker | `core/live/`, `core/cloud/` | P1 |
| P3 Playback API | `api/`, `m2t-desktop/` | P1 |
| P4 CLI download | `cli/` | P2 |
| P5 post_process | `core/live/post_process.py` | P2 |

**Lanes:** A = P0→P1→P2（sequential `core/live/`）  
B = P3 UI（after P1 API 契约冻结，可与 P2 尾段并行）  
C = P4（after P2）

**冲突:** P2 与 P5 同改 `post_process.py` → P5 最后合并。

### ASCII — 目标数据流（补 spec §3）

```
[stream URL]
     │
     ├─► ffmpeg HLS ──► parts/seg-*.m4s + master.m3u8  (Tier-0 LW-01)
     │
     └─► ffmpeg PCM ──► Deepgram WS ──► transcript.json (Tier-0 LW-02)

SegmentWatcher (daemon thread)
     │ part closed
     ▼
SegmentWorkerPool (Tier-1)
     compress? → upload part → delete_local → refresh cloud m3u8
     │
finalize (LW-05)
     ├─ seal transcript / ENDLIST
     ├─ upload sidecars (once)
     └─ enqueue summarize only (Tier-2)
```

### 架构决议（2026-06-09 用户确认）

| Eng | Spec | 选项 |
|-----|------|------|
| ER-D1 | D11 | SegmentWatcher |
| ER-D2 | D12 | segment 先于 post_process |
| ER-D3 | D13 | HLS DISCONTINUITY |
| ER-D4 | D14 | DB 权威 |
| ER-D5 | D15 | finalize sidecar |
| ER-D6 | D16 | 每段重传 m3u8 |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | stale | 2026-05-21 issues |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | **CLEAR (PLAN)** | D11–D16 adopted; plan written |
| Design Review | `/plan-design-review` | UI/UX (hls.js) | 1 | stale | 2026-06-04 |
| DX Review | `/plan-devex-review` | CLI download DX | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** Eng Review **CLEARED** — 可开工 [implementation plan](../plans/2026-06-09-live-segment-media-pipeline.md)

### Completion summary

- Step 0: Scope accepted MVP = P0–P3；P4/P5 defer OK
- Architecture: **6** issues（D1–D6）
- Code quality: **4**
- Test: diagram yes, **26** gaps, **2** CRITICAL regression
- Performance: **4**
- Outside voice: skipped（可 `/plan-eng-review` 后补 Codex）
- Lake score: 6/6 推荐完整选项（Watcher、调度顺序、DB 权威等）
