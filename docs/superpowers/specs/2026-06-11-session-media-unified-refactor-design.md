# Session Media 统一重构 — 录制 / 压缩 / 上云 / 播放

**日期:** 2026-06-11  
**状态:** Eng Review 通过（2026-06-11）；[implementation plan](../plans/2026-06-11-session-media-unified.md) + Epic issues [#296–#302](../../issues/README.md#session-media-unified-refactor2026-06-11待实现)  
**前置:** [Live Segment Media Pipeline](./2026-06-09-live-segment-media-pipeline-design.md)（LSM）、[Live Streaming STT v3](./2026-06-03-live-streaming-stt-design.md)、[Local Pipeline Refactor](./2026-06-08-m2t-local-pipeline-refactor-design.md)  
**被依赖:** Epic `session-media-unified`（[#296–#302](../../issues/README.md#session-media-unified-refactor2026-06-11待实现)）、G1–G4 gap 收尾、VOD 云播、压缩 PoC 重验  
**动机:** 用户从「整 MP4 上云」演进到「边录边压、边传边删」；LSM Epic 已交付分段 HLS + 段级上云，但 **管线分叉、压缩未开、播放未统一、VOD 未覆盖**，需收拢为单一 Session Media 模型。

---

## 0. 已锁定决策（本 spec 新增 / 修订）

| # | 决策 | 理由 |
|---|------|------|
| U1 | **唯一推荐生产路径：** `streaming` + `media.format=hls` + `segment_pipeline` | 已验证分段腾盘；与 LSM D1–D16 一致 |
| U2 | **压缩 = 录制时一次编码**（`encode` profile）；**废弃**「段后 async 压缩」作为产品路径 | LSM D3；`segment_process` 今日无二次压；避免双遍编码 |
| U3 | **云盘 session 目录为长期真相**；本地为滑动缓存 | 上传成功段可删本地；播放走统一 resolver |
| U4 | **历史播放契约：** 直播归档统一 `playback.m3u8` + part proxy；**禁止** Desktop 因 `discontinuity_at` 强制 remux MP4 | 断流场 + 云删本地当前无法播（见 §7） |
| U5 | **VOD（作品）** 纳入同一 **MediaResolver**：本地文件 → 云 Range 代理 → 下载恢复 | 用户场景 2 对作品同样成立 |
| U6 | **Legacy**（`pipeline_mode=legacy`、finalize 整 MP4 upload）标记 **deprecated**；保留 ≥2 release 只读兼容 | 减维护面；新 session 不走 |
| U7 | **PoC 门禁保留**：`encode.mode=compress` 默认真 **仅在** 目标硬件 PoC 通过后切换 example 默认 | LSM S6 未过（Intel HEVC VT） |
| U8 | **直播预览** 仍用平台 FLV 代理（`stream/proxy`）；与归档媒体路径分离 | 不读本地录制文件；与 LSM 无关 |
| U9 | **R2（播放统一）不依赖 R0（压缩 PoC）** | 用户断流云播痛点与编码无关；可并行交付 |
| U10 | **`playback.m3u8` 本地缺失时回退云 master**（合成 API playlist） | 仅删 `.m4s` 时 master 仍本地；整目录丢失须可播 |
| U11 | **云 part 用 API Range 代理**（非裸 302）；302 仅过渡 | Aliyun `download_url` 过期会破坏长时 hls.js 拉段 |
| U12 | **VOD R3 仅云播**；作品上云 defer 到 R3b / 独立 issue | 缩小 R3；播放 resolver 先统一 |
| U13 | **`SessionPlaybackService` = 薄服务**（`api/services/session_playback.py`） | 复用 `playback.py` 路由；不新建跨层大抽象 |

---

## 1. 问题陈述与用户需求（重新整理）

### 1.1 演进脉络

| 阶段 | 用户目标 | 技术含义 |
|------|----------|----------|
| A | 直播录下来 → 一个 MP4 → 上传云盘 | 单文件归档、整文件 upload |
| B | 视频多了占空间 → **边录边压缩** | 录制时编码降码率，禁止 copy 大文件后再压 |
| C | 长跑直播磁盘峰值高 | **分段闭合即上传、删本地段** |
| D | 转写 + 桌面体验 | Tier 隔离；STT 与视频分段正交 |
| E | 本地删了也要能看 | **云播**（流式），非必须先下载 |

### 1.2 核心诉求（第一性原理）

1. **存储效率**：本地峰值可控；云盘体积可控（依赖编码 profile，非仅换容器）。
2. **时效性**：段闭合后尽快上云；finalize 不阻塞整文件 remux/upload。
3. **可靠性**：上传/编码失败不停录；段级可重试。
4. **体验一致**：录什么、存什么、播什么 — **一种播放契约**，不按 legacy/hls/vod 各搞一套 UI 分支。

### 1.3 两个产品场景（验收锚点）

| 场景 | 描述 | 当前 |
|------|------|------|
| **S1 直播中** | Desktop 同步看直播；后台录制 + 云备份并行 | ✅ FLV 代理 + Tier-0 录制 |
| **S2 历史回放** | 本地无媒体时，从云盘流式播放（直播 + 作品） | ⚠️ 直播 HLS 部分；断流/remux 缺口；VOD ❌ |

**参考场次（dogfood）：** `20260611T110019Z` — `media_format=hls`，多段 `uploaded`，`discontinuity_at=[630.76]`，部分 `.m4s` 已删本地；Desktop 走 `playback.mp4` remux 路径失败。

---

## 2. 现网实现快照（2026-06-11）

### 2.1 并存管线矩阵

| 管线 | 配置 | 产物 | 压缩 | 上云 | finalize |
|------|------|------|------|------|----------|
| Legacy | `pipeline_mode=legacy` | FLV → **MP4** | ❌ | 整文件 `post_process` | remux MP4 |
| Streaming+FLV | `streaming` + `format=flv` | FLV（可选 MP4） | ❌ | 整文件 | 可选 remux |
| **Streaming+HLS** | `streaming` + `format=hls` | m3u8 + `.m4s` | ⚙️ `compress.enabled` | **段级** `segment_process` | 无整 MP4；sidecar only |
| 压缩 PoC | `compress.enabled=true` | HEVC VT → HLS | 代码有 | 同 HLS | — |

**配置分裂：**

| 项 | `AppConfig` 默认 | `config.example.yaml` |
|----|------------------|------------------------|
| `pipeline_mode` | `legacy` | `streaming` |
| `media.format` | `flv` | `flv` |
| `compress.enabled` | `false` | `false` |
| `segment_pipeline.enabled` | `true` | `true` |

用户实际 HLS 场次说明 **`config.yaml` 已设 `format=hls`**，与 example 推荐 FLV 不一致。

### 2.2 LSM Epic 交付 vs 缺口

| 能力 | LSM spec | 代码现状 |
|------|----------|----------|
| HLS 分段录制 | D1 | ✅ `hls_recorder.py` |
| SegmentWatcher + upload | D11–D12 | ✅ |
| DB 权威 parts | D14 | ✅ `live_session_parts` |
| 播放 API | D7 | ✅ `playback.m3u8` + part 云 302 |
| Desktop hls.js | D7 | ⚠️ 有 `discontinuity_at` 时 **不用** hls.js |
| 压缩默认开 | D2 + S6 | ❌ 默认关；PoC **未通过**（Intel） |
| 段后 async 压 | §3 Tier-1 | ❌ 未实现（且 U2 废弃） |
| VOD 云播 | — | ❌ |
| Legacy 整 MP4 云播 | — | ❌ |

**关联 gap issues：** G1（DISCONTINUITY 已关）、G2（S4 对齐）、G3（段 job 重试）、G4（云 init/mp4 manifest）。

### 2.3 播放路径分裂（根因）

```
直播预览:     stream/proxy → 平台 FLV     (session status=recording|remuxing)
历史 HLS:     playback.m3u8 → hls.js      (仅 discontinuity_at 为空)
历史 HLS+断流: playback.mp4 → ffmpeg remux  (需本地 .m4s，云删则失败)
历史 MP4/FLV: /api/media 本地 FileResponse  (无云回退)
VOD 作品:     /api/media 仅本地            (cloud_not_supported_for_vod)
```

---

## 3. 目标架构

### 3.1 数据流（统一后）

```
[平台 stream URL]
     │
     ├─► ffmpeg HLS (encode profile) ──► parts/seg-*.m4s + master.m3u8   [Tier-0 LW-01]
     │
     └─► ffmpeg PCM ──► Deepgram WS ──► transcript.json                  [Tier-0 LW-02]

SegmentWatcher → segment_process_jobs
     │
     ▼
SegmentWorkerPool [Tier-1]
     upload part → refresh cloud master.m3u8 → delete_local (.m4s only)

finalize [Tier-0 LW-05 + Tier-2]
     seal transcript / ENDLIST
     upload sidecars (once)
     enqueue summarize only
     禁止: remux 整场 MP4、maybe_upload 整文件（HLS session）

Playback [API + Desktop]
     session_playback.resolve(session) → { kind: hls|mp4, playlist_url }
     master.m3u8 本地 → rewrite URIs → API parts
     master 仅云 → DB cloud_uploads 拉云 m3u8 → 同样 rewrite（U10）
     part: 本地 FileResponse(Range)  else API 代理 Aliyun(Range)（U11）
```

### 3.2 Session Media 抽象

**单一领域模型**（DB + 物化 manifest）：

```text
LiveSessionMedia
  session_id
  media_format: hls | mp4 | flv          # 新 session 仅 hls；其余只读
  encode_profile: { mode, codec, v_bitrate, a_bitrate }
  parts[]: LiveSessionPart              # HLS 权威在 live_session_parts
  discontinuity_at[]: float[]           # 秒，播放时间轴用
  cloud_anchor: string                   # 云目录锚点（timestamp）
  playback_mode: hls | mp4 | flv        # 对外播放形态（可不同于 encode 容器）
```

**Part 状态机**（与 LSM 一致，不新增）：

`recording → closed → ready → uploading → uploaded → local_deleted | failed`

### 3.3 Tier 职责（与 LSM 对齐，finalize 瘦身）

| Tier | 职责 | 禁止 |
|------|------|------|
| Tier-0 | HLS encode、STT、重连 DISCONTINUITY、finalize seal | await upload/compress |
| Tier-1 | 段 upload、云 m3u8 刷新、删本地段 | 二次压缩（U2） |
| Tier-2 | summarize、sidecar 补传 | 整文件 remux/upload（HLS） |

### 3.4 Encode Profile（替代散落 `compress.*`）

```yaml
live:
  pipeline_mode: streaming
  media:
    format: hls
    segment_duration_sec: 600
  encode:
  # 新配置块；迁移期与 live.compress 双读，最终只保留 encode
    mode: copy | compress              # 默认 compress（PoC 通过后）
    video_codec: auto                  # auto → hevc_videotoolbox (Apple) / h264_videotoolbox / libx264
    video_bitrate: 2M
    audio_codec: aac
    audio_bitrate: 128k
  segment_pipeline:
    enabled: true
    upload:
      enabled: true
      delete_local_after_upload: true
```

**`auto` 选型规则：**

1. Apple Silicon + PoC 通过 → `hevc_videotoolbox`
2. Apple 但 HEVC 失败 → `h264_videotoolbox`
3. 无 VideoToolbox → `libx264`（CPU，需 PoC 测 realtime）
4. 全部不满足 → `mode: copy` + 文档告警

### 3.5 云盘布局（不变，D6）

```text
media2text/{platform}/{nickname}/live/{anchor}/
  master.m3u8
  init.mp4                    # G4：须保证云上有 init
  parts/seg-*.m4s
  {anchor}.transcript.*
  {anchor}.summary.*
```

**不**在云端 merge 单 MP4。整场 MP4 仅 **按需** CLI：`live download --merge`。

---

## 4. 统一播放层（Session Playback Service）

### 4.1 原则

- **一种主路径：** HLS event playlist + hls.js（直播归档）。
- **一种回退：** MP4 Range（Legacy 历史、单文件 VOD）。
- **Resolver 顺序：** 本地可读 → API 云代理 → 提示下载恢复。

### 4.2 API（修订 / 新增）

| 端点 | 行为 | 变更 |
|------|------|------|
| `GET /api/sessions/{id}/playback.m3u8` | EVENT playlist；part/init URI → API | **新增** 本地 master 缺失时读云 m3u8（U10） |
| `GET /api/sessions/{id}/parts/{index}` | 本地或 **API 流式代理**（Range 透传） | U11：替代裸 302；init 同路由 |
| `GET /api/sessions/{id}/playback.mp4` | ffmpeg remux | **deprecated**；仅 legacy 只读 |
| `GET /api/media?path=...` | 本地 `FileResponse` | **新增** 云 Range 回退（VOD + legacy MP4） |
| `GET /api/vod/{aweme_id}/playback` | VOD 专用 Range | **新增**（可选与 media 合并） |

**`cloud_available` 语义：** session / aweme 在 DB 或 manifest 标明云路径且 `aliyundrive` 已登录。

### 4.3 Desktop `ViewPlayback` 变更（U4）

| 现状 | 目标 |
|------|------|
| `discontinuity_at.length > 0` → `playbackMp4Url` | **始终** `playbackM3u8Url` + hls.js |
| 断流 seek | `alignPlaybackTime` + `EXT-X-DISCONTINUITY`（G2） |
| VOD 仅 `mediaUrl` | `mediaUrl` 云回退或 `/api/vod/.../playback` |
| `sessionCanDownloadCloud` 仅 live | 扩展 VOD（若上云） |

### 4.4 直播预览（不变，U8）

`GET /api/sessions/{id}/stream/proxy` — 平台 HTTP-FLV，`status ∈ {recording, remuxing}`。与 Session Media 归档解耦。

---

## 5. VOD（作品）纳入

### 5.1 范围

- **播放：** 本地 `videos/{id}.mp4` 缺失时，若 manifest / DB 有 `cloud_path`，API Range 代理阿里云。
- **上传（可选 Phase）：** `download run` 或 `pipeline run` 完成后 `maybe_upload_vod_to_aliyundrive`（镜像 live 侧car 策略）。
- **DB：** `awemes.cloud_path` / `cloud_file_id` / `uploaded_at`（或复用 `cloud_uploads` 表）。

### 5.2 非目标

- 作品转 HLS 分段（单 MP4 Range 足够）。
- 云端转码。

---

## 6. Success Criteria

| ID | 指标 | 目标 |
|----|------|------|
| US1 | 新 session 默认路径 | 100% `streaming+hls+segment`（无 legacy 新录） |
| US2 | 本地磁盘峰值 | ≤ 2 × segment_size（S1 继承） |
| US3 | 压缩生效后云盘体积 | ≤ 原 copy 码率 **40%**（S6 继承，PoC 硬件） |
| US4 | 断流场次云播 | `discontinuity_at` 非空 + 本地段已删 → Desktop **可播** hls.js |
| US5 | VOD 云播 | 本地删 MP4、云有备份 → 可 seek 播放 |
| US6 | Legacy 兼容 | 旧 MP4/FLV 场次只读播放不退化 |
| US7 | 故障隔离 | upload/encode 失败不停录（S5 继承） |
| US8 | STT | finalize 封存 ≤10s（v3 回归） |
| US9 | 云 master 回退 | 本地无 `master.m3u8`、云有 m3u8 → `playback.m3u8` 200 |
| US10 | Part 代理 Range | hls.js seek 跨段；无 302 URL 过期断播 |

---

## 7. 分阶段交付（Epic 建议）

| Phase | 名称 | 内容 | 依赖 |
|-------|------|------|------|
| **R0** | Encode PoC | Apple Silicon 重跑 S6；`encode.mode=compress` 门禁；Intel fallback 矩阵 | — |
| **R1** | Config 收拢 | `config.example` → `hls` 默认；`encode` 块；文档「唯一推荐路径」 | R0 可选 |
| **R2** | 播放统一 | 去 `hlsNeedsRemux`；part 云代理 Range；G1/G2/G4 | LSM-3 |
| **R3** | VOD 云播 | `/api/media` 云 Range 回退；Desktop VOD | aliyundrive |
| **R3b** | VOD 上云（可选） | `maybe_upload_vod` + DB 字段 | R3 播放验收后 |
| **R4** | Legacy 退场 | deprecation 日志；HLS finalize 删 remux 分支；post_process 删整文件 upload（HLS） | R2 |
| **R5** | 硬化 | 段 job 重试（G3）；云 302→代理；监控指标 | R2 |

**与现有 issue 映射：**

- R0 → `live-segment-lsm0-compress-poc`（重开验收）
- R2 → G1（已关）、G2、G4
- R5 → G3

---

## 8. 迁移与兼容

### 8.1 已有 session

| 类型 | 播放 | 上云 |
|------|------|------|
| Legacy MP4 | `/api/media` 或云 Range（R3 后） | 已有整文件云路径 |
| Streaming FLV | `/api/media` 或 remux | 整文件 |
| HLS 分段 | `playback.m3u8`（R2 后全量 hls.js） | 段目录镜像 |

**不迁移** 历史 session 到 HLS；只保证只读播放。

### 8.2 配置迁移

```yaml
# 旧
live.compress.enabled: true
live.compress.video_bitrate: 2M

# 新（双读一 release）
live.encode.mode: compress
live.encode.video_bitrate: 2M
```

### 8.3 CLI / agent-manifest

- `agent-manifest.json`：`playback_mode`、`parts[]`、`cloud_available` 由 DB 物化（已有）。
- `live download --merge` 保持（LSM-4）。

---

## 9. 模块变更清单

| 模块 | 变更 |
|------|------|
| `core/config.py` | `LiveEncodeConfig`；`compress` → `encode` 迁移 |
| `core/live/hls_recorder.py` | 读 `encode` profile；codec auto |
| `core/live/recording.py` | HLS finalize 删除 remux MP4 分支（R4） |
| `core/live/post_process.py` | HLS 跳过整文件 upload（强化）；legacy 保留 |
| `core/live/segment_process.py` | 无 async compress（U2） |
| `api/routes/playback.py` | part 云代理 Range；init.mp4 |
| `api/routes/media.py` | 云 Range 回退 |
| `api/services/history_media.py` | VOD 云下载/播放 |
| `apps/m2t-desktop/.../ViewPlayback.tsx` | 去 remux 分支；VOD 云 |
| `config.example.yaml` | `format: hls`；`encode` 默认 |
| `docs/issues/README.md` | Epic `session-media-unified` 条目 |

---

## 10. 测试策略（摘要）

| 区域 | 必测 |
|------|------|
| Encode | PoC 脚本 + `test_hls_recorder` codec 分支 |
| 播放 | `test_playback_api` 云 part、断流 m3u8、init |
| Desktop | `ViewPlayback.test.tsx`：断流场 mock hls.js，无 remux |
| 回归 | `test_streaming_stt_finalize` ≤10s |
| E2E | 2 段上传删本地 → 仅云 part 可播 |
| VOD | `test_api_media_cloud_fallback` |

---

## 11. 非目标

- 云端 merge MP4 / 服务端转码
- 抖音/B 站「模拟直播」从云推流（仅播放 seek）
- 替换阿里云盘为其他云
- 段后 async 二次压缩（U2 废弃）
- 实时预览改读本地 HLS（仍用平台 FLV）

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Intel Mac 无法 HEVC 实时编码 | `encode.video_codec: auto` fallback x264；默认 copy |
| 云 part 302 URL 过期 | R5 API 代理替代裸 302 |
| 断流 seek 错位 | G2 `duration_sec` / `discontinuity_at` 对齐 |
| init.mp4 未上云 | G4 验收 |
| Legacy 用户 config 仍为 `legacy` | R1 文档 + doctor 警告 |

---

## 13. Eng Review 决议（2026-06-11）

| # | 问题 | 决议 |
|---|------|------|
| O1 | 云 part 交付 | **API Range 代理**（R2 实现核心；R5 删 302 路径）— U11 |
| O2 | VOD 上云时机 | **R3 仅播放**；上云 **R3b** defer — U12 |
| O3 | `encode` 默认 | PoC 通过前 example **`mode: copy`**；通过后 **`compress`** + doctor 提示硬件 |
| O4 | Legacy 退场 | **R4 deprecation 日志**；删代码 ≥2 release 后独立 issue |
| ER1 | `SessionPlaybackService` 范围 | 薄服务 + 现有 router；**不**新领域层 — U13 |
| ER2 | 播放与压缩阶段 | **R2 先于/并行 R0** — U9 |
| ER3 | 云仅 master | `playback.m3u8` **必须**云 master 回退 — U10 |
| ER4 | playlist 缺段 | part 404 → hls.js 错误面；API 标 `missing_parts[]`；不伪造空段 |
| ER5 | `compress`→`encode` 迁移 | **单 release**：loader 读 `encode`，`compress` 作 deprecated alias |

### 13.1 What already exists（复用，勿重写）

| 已有 | 用途 |
|------|------|
| `hls_recorder.py` + `LiveCompressConfig` | 录制编码；扩 `encode` + `auto` codec |
| `segment_process.py` + `upload_live_part` | Tier-1 段上传 + 云 m3u8 刷新 |
| `playback.py` + `_rewrite_m3u8` | playlist 重写 + part 302 |
| `playback_remux.py` | remux 路径 **deprecated**，legacy 只读保留 |
| `post_process` `is_hls_session_media` skip | HLS 整文件 upload 已 skip |
| `ViewPlayback` + `alignPlaybackTime` | 断流时间轴；去 `hlsNeedsRemux` 即可 |
| `history_media.download_from_cloud` | live 下载；VOD 需对称 Range 播放 |
| G1–G4 gap issues | R2/R5 直接挂接 |

### 13.2 NOT in scope（显式 defer）

| 项 | 理由 |
|----|------|
| 云端 merge MP4 | D6；CLI `--merge` 足够 |
| 段后 async 压缩 | U2 |
| 模拟直播推流 | 仅 seek 播放 |
| 换云厂商 | Aliyun 个人版路径已定型 |
| `SessionMedia` 新 DB 表 | `live_session_parts` + `cloud_uploads` 够用 |
| R0 Intel HEVC 硬解 | fallback x264 PoC 子项，不阻塞 R2 |

---

## 14. 参考

- LSM 设计：[2026-06-09-live-segment-media-pipeline-design.md](./2026-06-09-live-segment-media-pipeline-design.md)
- 压缩 PoC 验收：[verification/2026-06-09-live-compress-benchmark.md](../verification/2026-06-09-live-compress-benchmark.md)
- Gap issues：`docs/issues/live-segment-gap-g1` … `g4`
- Dogfood manifest：`data/creators/.../live/20260611T110019Z/session.manifest.json`

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | 可选：VOD 上云是否产品默认 |
| Codex Review | `/codex review` | 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | **CLEAR (PLAN)** | 8 决议；2 critical gaps 已入 spec |
| Design Review | `/plan-design-review` | hls.js 断流 UX | 0 | — | R2 前建议跑 |
| DX Review | `/plan-devex-review` | `encode` 迁移 | 0 | — | R1 前建议跑 |

- **UNRESOLVED:** 0（O1–O4 + ER1–ER5 已锁）
- **VERDICT:** Eng **CLEARED** — 可写 plan `docs/superpowers/plans/2026-06-11-session-media-unified.md` 并开 Epic

### Eng Review 摘要

- **Step 0:** 范围接受；R3 拆播放/上云；不新建 SessionMedia DB
- **Architecture:** 5 issues → U9–U13 + ER3/ER4
- **Critical gaps:** (1) 云 master 回退缺失 (2) 302 过期 — 已写入 U10/U11
- **Tests:** 见 §10 + test plan `~/.gstack/projects/media2text/`
- **Parallel lanes:** R0 ∥ R2；R3 after R2；R4 after R2
