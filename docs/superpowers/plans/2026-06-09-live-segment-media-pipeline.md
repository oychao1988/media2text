# Live Segment Media Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-FLV live recording with HLS fMP4 segments, async per-part cloud upload with default local delete, hls.js playback, while keeping streaming STT and Tier isolation (record/STT never blocked by upload/compress).

**Architecture:** Three tiers per [spec](../specs/2026-06-09-live-segment-media-pipeline-design.md): Tier-0 (`hls_recorder` + existing `streaming_stt`), `SegmentWatcher` + Tier-1 `SegmentProcessPool`, Tier-2 post_process summarize-only. DB (`live_session_parts`) is source of truth; `session.manifest.json` exported on finalize.

**Tech Stack:** Python 3.12+, ffmpeg HLS, SQLite, FastAPI sidecar, Vitest/hls.js, pytest, existing `PostProcessExecutor` / `TaskSchedulerLoop` patterns.

**Spec:** [2026-06-09-live-segment-media-pipeline-design.md](../specs/2026-06-09-live-segment-media-pipeline-design.md) (D11–D16 locked).

**MVP merge target:** P0–P3. P4–P5 as follow-up PRs.

---

## PR 拆分（推荐顺序）

| PR | Phase | 主题 | 依赖 |
|----|-------|------|------|
| **LSM-0** | P0 | 压缩 PoC + 验收表 | — |
| **LSM-1** | P1 | Schema + manifest + `hls_recorder` + LW-03 + recording 接入 | LSM-0 可选 |
| **LSM-2** | P2 | SegmentWatcher + SegmentProcessPool + 段级 aliyun + scheduler 顺序 | LSM-1 |
| **LSM-3** | P3 | Playback API + Desktop hls.js | LSM-1（契约）；与 LSM-2 可并行 |
| **LSM-4** | P4 | CLI `live download` | LSM-2 |
| **LSM-5** | P5 | post_process 瘦身 + agent-manifest + docs | LSM-2 |

**冲突注意:** LSM-2 与 LSM-5 同触 `post_process.py` — LSM-5 在 LSM-2 合并后开分支。

---

## LSM-0 — Phase 0：压缩 PoC（门禁）

### Task 0.1: Benchmark 脚本

**Files:**
- Create: `scripts/benchmark_live_compress.py`
- Create: `docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`

- [ ] **Step 1:** 脚本接受本地 FLV/TS 或短录样本，跑 `hevc_videotoolbox` + HLS 参数（spec §7），输出体积比、VT realtime 倍率、CPU%。
- [ ] **Step 2:** 验收表填 S6 门槛（≤40% 体积、≥1.0× realtime）；未通过则 `live.compress.enabled` 保持 false。
- [ ] **Step 3:** 在 `config.example.yaml` 注释 PoC 门禁（不默认 true）。

**验证:**

```bash
python scripts/benchmark_live_compress.py --sample data/creators/.../live/*.flv --json
```

---

## LSM-1 — Phase 1：HLS 录制 + DB + LW-03

### Task 1.1: DB migration + repos

**Files:**
- Modify: `src/media2text/core/storage/db.py`
- Modify: `src/media2text/core/storage/repos.py`
- Create: `src/media2text/core/live/segment_manifest.py`
- Test: `tests/unit/test_segment_manifest.py`

- [ ] **Step 1: Failing test — upsert part + state machine**

```python
def test_live_session_part_state_transitions(tmp_path):
    repo.upsert_part(session_id="s1", part_index=1, rel_path="parts/seg-00001.m4s", state="recording")
    repo.mark_closed("s1", 1)
    row = repo.get_part("s1", 1)
    assert row.state == "closed"
```

- [ ] **Step 2:** 建表 `live_session_parts`、`segment_process_jobs`；`cloud_uploads` 增 `part_index INTEGER`（nullable）。
- [ ] **Step 3:** `SegmentManifestRepo`：`upsert_part`, `mark_closed`, `mark_uploaded`, `mark_local_deleted`, `list_parts`, `export_json(session_id)`.
- [ ] **Step 4:** `pytest tests/unit/test_segment_manifest.py -v`

### Task 1.2: `hls_recorder.py`

**Files:**
- Create: `src/media2text/core/live/hls_recorder.py`
- Modify: `src/media2text/core/ffmpeg.py`（或集中 HLS argv 构建）
- Test: `tests/unit/test_hls_recorder.py`

- [ ] **Step 1: Failing test — build HLS ffmpeg args**

```python
def test_hls_recorder_builds_event_playlist_args():
    args = build_hls_recorder_args(url="http://...", out_dir=tmp, segment_sec=600, compress_cfg=...)
    assert "-f" in args and "hls" in args
    assert "-hls_playlist_type" in args
```

- [ ] **Step 2:** `spawn_hls_recorder()` → `subprocess.Popen`；输出 `session_dir/master.m3u8` + `parts/seg-%05d.m4s`。
- [ ] **Step 3:** `stop_hls_recorder()` 优雅 SIGINT；finalize 时写 ENDLIST（或 ffmpeg `-hls_flags append_list+omit_endlist` 关闭）。

### Task 1.3: LW-03 重连（D13）

**Files:**
- Modify: `src/media2text/core/live/hls_recorder.py`
- Modify: `src/media2text/core/live/recording.py`（`_reconnect_segment` HLS 分支）
- Test: `tests/unit/test_hls_recorder.py`

- [ ] **Step 1: Failing test — reconnect increments index + discontinuity**

```python
def test_hls_reconnect_appends_discontinuity_and_new_index():
    # simulate stop + rotate with existing parts 1..2
    rotate_hls_after_reconnect(session_id, next_index=3, discontinuity_seq=1)
    text = (session_dir / "master.m3u8").read_text()
    assert "EXT-X-DISCONTINUITY" in text
    assert repo.get_part(..., 3) is not None
```

- [ ] **Step 2:** 实现 `rotate_hls_after_reconnect`；DB `discontinuity_seq` + `discontinuity_at[]` 在 export JSON。
- [ ] **Step 3:** `recording.py`：当 `live.media.format=hls` 时走 HLS 重连，**不** concat FLV。

### Task 1.4: Config + recording 主路径切换

**Files:**
- Modify: `src/media2text/core/config.py`
- Modify: `config.example.yaml`
- Modify: `src/media2text/core/live/recording.py`
- Test: `tests/unit/test_live_recording_hls.py`（新建或扩展现有 recording 测试）

- [ ] **Step 1:** 增 `live.media.*`、`live.compress.*`、`live.segment_pipeline.*`（spec §9）。
- [ ] **Step 2:** `pipeline_mode=streaming` + `media.format=hls` → LW-01 用 `hls_recorder`；`flv_legacy` / `format=flv` 保持现网。
- [ ] **Step 3:** 会话目录从 `live/{timestamp}.flv` 改为 `live/{anchor}/`（与 spec §4 一致）；`live_sessions` 记 `session_dir`。
- [ ] **Step 4:** **REGRESSION** — `streaming_stt` 仍并行；finalize ≤10s 不 await upload。

```bash
pytest tests/unit/test_hls_recorder.py tests/unit/test_live_recording*.py tests/unit/test_streaming_stt*.py -v
```

---

## LSM-2 — Phase 2：SegmentWatcher + Tier-1 上传

### Task 2.1: `segment_watcher.py`（D11）

**Files:**
- Create: `src/media2text/core/live/segment_watcher.py`
- Modify: `src/media2text/core/live/scheduler.py`（daemon 启动 watcher 线程）
- Test: `tests/unit/test_segment_watcher.py`

- [ ] **Step 1: Failing test — stable mtime closes part and enqueues job**

```python
def test_watcher_closes_stable_segment_and_enqueues_job(tmp_path, monkeypatch):
    # touch seg-00001.m4s, advance mtime, run watcher.tick_once()
    assert SegmentProcessJobRepo(conn).has_pending("s1", part_index=1)
```

- [ ] **Step 2:** 实现 poll；跳过 growing file；`dedupe segment_process:{session_id}:{index}`。
- [ ] **Step 3:** finalize 时 watcher 停表 + 末段 force close。

### Task 2.2: `segment_process.py` + pool

**Files:**
- Create: `src/media2text/core/live/segment_process.py`
- Create: `src/media2text/core/live/segment_process_pool.py`
- Modify: `src/media2text/core/cloud/live_upload.py`（段级 `upload_part`）
- Test: `tests/unit/test_segment_process.py`

- [ ] **Step 1: Failing test — upload then delete only when uploaded**

```python
def test_segment_process_deletes_local_only_after_upload_confirmed(monkeypatch, tmp_path):
    monkeypatch.setattr("...upload_live_part", lambda **k: {"ok": True, "cloud_path": "..."})
    run_segment_process_job(cfg, conn, job_id=...)
    assert not part_path.exists()
    assert repo.get_part(...).state == "local_deleted"
```

- [ ] **Step 2:** 主路径跳过 async compress（`compress.enabled` 且 HLS 已编码）；失败时 upload 原段。
- [ ] **Step 3:** 上传后 **重传** `master.m3u8`（D16）；更新 `cloud_uploads` 含 `part_index`。
- [ ] **Step 4:** `SegmentProcessExecutor` 仿 `PostProcessExecutor`：worker 独立 `open_db`。

### Task 2.3: Scheduler 顺序（D12）— **CRITICAL**

**Files:**
- Modify: `src/media2text/core/live/task_scheduler.py`
- Modify: `src/media2text/core/live/scheduler.py`（构造并注入 segment pool）
- Test: `tests/unit/test_task_scheduler_segment_order.py`

- [ ] **Step 1: Failing test**

```python
def test_scheduler_drains_segment_process_before_post_process():
    calls = []
    # mock segment_pool.drain → append "segment"
    # mock post_pool.drain → append "post"
    loop.tick_once(conn)
    assert calls.index("segment") < calls.index("post")
```

- [ ] **Step 2:** 在 `post_pool.drain_pending` **之前** 调用 `segment_pool.drain_pending`。
- [ ] **Step 3:** `pytest tests/unit/test_task_scheduler.py tests/unit/test_task_scheduler_segment_order.py -v`

### Task 2.4: Finalize sidecar 上传（D15）

**Files:**
- Modify: `src/media2text/core/live/recording.py`（`_finalize_recording_streaming`）
- Modify: `src/media2text/core/cloud/live_upload.py`
- Test: `tests/unit/test_segment_finalize_sidecar.py`

- [ ] **Step 1:** finalize 路径：封存 STT → ENDLIST → `export_session_manifest_json` → **单次** upload transcript/summary/manifest（非 per-part）。
- [ ] **Step 2:** 移除 streaming finalize 内整文件 MP4 upload / concat（D9）。
- [ ] **Step 3:** post_process job 仅 enqueue summarize（若 enabled），无 upload 阶段。

---

## LSM-3 — Phase 3：Playback API + Desktop

### Task 3.1: Playback API

**Files:**
- Create: `src/media2text/api/routes/playback.py`
- Modify: `src/media2text/api/app.py`
- Modify: `src/media2text/api/routes/media.py`（`.m3u8` / `.m4s` content-type）
- Test: `tests/unit/test_playback_api.py`

- [ ] **Step 1: Failing test — serve local master.m3u8**

```python
def test_playback_m3u8_returns_event_playlist(client, session_with_hls):
    r = client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert "EXTM3U" in r.text
```

- [ ] **Step 2:** `GET /api/sessions/{id}/playback.m3u8` — 本地 `session_dir/master.m3u8`。
- [ ] **Step 3:** `GET /api/sessions/{id}/parts/{index}` — 本地 part 或 302 cloud（`local_deleted` + 云存在）。
- [ ] **Step 4:** m3u8 内 part URI 走 API 路径（非裸文件路径）。

### Task 3.2: Desktop hls.js

**Files:**
- Modify: `apps/m2t-desktop/src/features/history/ViewPlayback.tsx`
- Modify: `apps/m2t-desktop/src/lib/api.ts`
- Modify: `apps/m2t-desktop/package.json`（`hls.js` 依赖）
- Test: `apps/m2t-desktop/src/features/history/ViewPlayback.test.tsx`

- [ ] **Step 1:** 检测 session `media_format=hls` → `Hls.loadSource(playbackM3u8Url)`；legacy 仍 flv.js（D10）。
- [ ] **Step 2:** `playbackTime` 对齐 transcript；`discontinuity_at` 偏移（S4）。
- [ ] **Step 3:** Vitest mock `hls.js`；无本地 part 时 cloud fallback 不崩。

```bash
pnpm --filter m2t-desktop test
pytest tests/unit/test_playback_api.py tests/unit/test_desktop_* -v -m desktop
```

---

## LSM-4 — Phase 4：CLI `live download`

### Task 4.1: `live download` 子命令

**Files:**
- Create: `src/media2text/cli/live_download.py`（或扩 `cli/live.py`）
- Test: `tests/unit/test_live_download_cli.py`

- [ ] **Step 1: Failing test — download all parts from cloud**

```bash
media2text live download <session_id> --parts all --json
# assert parts_downloaded == N
```

- [ ] **Step 2:** `--parts all|1,2,3`；默认 `--keep-local false`（仅拉取到临时或目标目录）。
- [ ] **Step 3:** `--merge` → ffmpeg concat demuxer → 单 MP4（S7）；失败时保留分段。

---

## LSM-5 — Phase 5：收尾

### Task 5.1: post_process + manifest 索引

**Files:**
- Modify: `src/media2text/core/live/post_process.py`
- Modify: `src/media2text/core/agent_manifest.py`（或等价刷新逻辑）
- Modify: `CLAUDE.md`、`README.md`（live 段落）
- Test: 现有 post_process 测试更新

- [ ] **Step 1:** `run_post_process_job` 删除 live 整文件 upload / remux 分支（HLS session）。
- [ ] **Step 2:** `agent-manifest.json` 增 `playback_mode: hls`、`parts[]` 摘要。
- [ ] **Step 3:** Epic 验收表 `docs/superpowers/verification/2026-06-09-live-segment-media-acceptance.md`（新建，勾 S1–S7）。

---

## 回归清单（每个 PR 必跑）

```bash
source .venv/bin/activate
pytest tests/unit/test_task_scheduler_segment_order.py tests/unit/test_streaming_stt*.py -v
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop  # LSM-3+
ruff check src tests
```

| 项 | 命令/文件 |
|----|-----------|
| GF-5 STT 不阻塞 finalize | `tests/unit/test_monitor_executor*.py` |
| Scheduler segment 先于 post | `test_task_scheduler_segment_order.py` |
| flv_legacy 未破坏 | `live.media.format=flv` 集成测试或标记 `@pytest.mark.live` |

---

## GSTACK REVIEW REPORT

| Review | Status |
|--------|--------|
| Eng Review (spec) | CLEAR — D11–D16 |
| Implementation | 待 LSM-0 起 PR |

**VERDICT:** Spec cleared；按 LSM-0 → LSM-1 → LSM-2 顺序开工。LSM-3 可在 LSM-1 API 契约冻结后并行。
