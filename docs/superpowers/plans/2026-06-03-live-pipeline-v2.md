# Live Pipeline v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple live detection from slow work so each stream is recorded within ~30s of detection, end-of-live is notified immediately, post-process runs in parallel without blocking other live polls, and every stage is timed and queryable.

**Architecture:** Three in-process executors — `LiveTickLoop` (10s, live only), `SlowTickLoop` (VOD/archive/dynamic), `PostProcessExecutor` (thread pool). Wall-clock offline confirmation replaces poll-count streak. New `live_pipeline_events` table + `live status` CLI for traceability.

**Tech Stack:** Python 3.12+, threading, SQLite WAL, existing LiveRecordingCore/post_process, Typer, pytest.

**Spec:** [2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md)（v1.2；eng review D1–D5 已锁定）

**Status:** **已交付（P0–P3 merged）**；最终验收见 [verification/2026-06-03-live-pipeline-v2-acceptance.md](../verification/2026-06-03-live-pipeline-v2-acceptance.md)。G3/G4/G1 下一场真实直播跟进。

---

## File map

| File | Responsibility |
|------|----------------|
| `src/media2text/core/live/scheduler.py` | `LiveTickLoop`, `SlowTickLoop`, daemon orchestration |
| `src/media2text/core/live/post_process_pool.py` | Thread-pool wrapper around `drain_pending_jobs` / single job submit |
| `src/media2text/core/live/pipeline_events.py` | Event emit helper + stage constants |
| `src/media2text/core/storage/db.py` | `live_pipeline_events` + session columns migration |
| `src/media2text/core/storage/models.py` | `PipelineEventRow`, extend `LiveSessionRow` |
| `src/media2text/core/storage/repos.py` | `PipelineEventRepo`, session timestamp helpers |
| `src/media2text/core/live/recording.py` | Emit events; wall-clock offline; `live_ended` notify |
| `src/media2text/core/live/post_process.py` | Emit per-stage events + `summarize_completed` notify |
| `src/media2text/core/monitor/watcher.py` | Delegate to scheduler (thin) |
| `src/media2text/core/config.py` | New LiveConfig fields |
| `src/media2text/core/notify/events.py` | `LIVE_ENDED`, `LIVE_START_FAILED`, `SUMMARIZE_COMPLETED` |
| `src/media2text/cli/live.py` | `live status`, `live timeline`, `live stats` |
| `src/media2text/cli/main.py` | Register `live` typer |
| `config.example.yaml` | Document new keys |
| `tests/unit/test_live_scheduler.py` | Thread isolation tests |
| `tests/unit/test_pipeline_events.py` | Event repo tests |
| `tests/unit/test_offline_wall_clock.py` | Offline confirm by seconds |
| `tests/unit/test_live_status_cli.py` | CLI JSON shape |

---

## P0 — Thread isolation (unblocks G1/G5)

### Task 1: PostProcessExecutor

**Files:**
- Create: `src/media2text/core/live/post_process_pool.py`
- Test: `tests/unit/test_post_process_pool.py`

- [ ] **Step 1: Write failing test — submit does not block caller**

```python
def test_submit_returns_immediately_while_job_runs(monkeypatch, tmp_path) -> None:
    import threading
    import time
    from media2text.core.live.post_process_pool import PostProcessExecutor

    barrier = threading.Event()
    def slow_job(*a, **k):
        barrier.wait(timeout=5)
        return {"ok": True}

    monkeypatch.setattr(
        "media2text.core.live.post_process_pool.run_post_process_job",
        slow_job,
    )
    pool = PostProcessExecutor(max_workers=1)
    t0 = time.monotonic()
    pool.submit(cfg=..., conn=..., job_id="j1", notify=...)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5
    barrier.set()
    pool.shutdown(wait=True)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/unit/test_post_process_pool.py -v`

- [ ] **Step 3: Implement PostProcessExecutor**

```python
class PostProcessExecutor:
    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="postproc")

    def submit(self, cfg, *, job_id: str, notify) -> None:
        """D1: worker opens its own DB connection — do not pass LiveTick conn."""
        def _run() -> None:
            conn = open_db(cfg)
            try:
                run_post_process_job(cfg, conn, job_id=job_id, notify=notify)
            finally:
                conn.close()

        self._executor.submit(_run)

    def drain_pending(self, cfg, conn, *, notify, limit: int) -> None:
        """Claim on caller conn; submit each job to pool (non-blocking)."""
        ...

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/live/post_process_pool.py tests/unit/test_post_process_pool.py
git commit -m "feat(live): PostProcessExecutor for non-blocking job drain"
```

---

### Task 2: LiveTickLoop + SlowTickLoop

**Files:**
- Create: `src/media2text/core/live/scheduler.py`
- Modify: `src/media2text/core/monitor/watcher.py`
- Test: `tests/unit/test_live_scheduler.py`

- [ ] **Step 1: Write failing test — live loop runs while slow job blocks**

Mock `_run_vod_tick` to sleep 30s on SlowTickLoop; assert LiveTickLoop `run_once` called ≥2 times in 5s wall time.

- [ ] **Step 2: Implement scheduler**

```python
class LiveTickLoop:
    """Dedicated thread: douyin + bilibili run_once only."""

class SlowTickLoop:
    """Dedicated thread: vod, archive, dynamic on their intervals."""

class MonitorScheduler:
    def __init__(self, watcher: MonitorWatcher, cfg: AppConfig) -> None: ...
    def start(self) -> None: ...  # spawn live + slow threads + post pool
    def stop(self) -> None: ...
```

`MonitorWatcher.run_daemon` becomes:

```python
def run_daemon(self, *, creator_id: str | None = None) -> None:
    with workspace_lock(...):
        scheduler = MonitorScheduler(self, self._cfg)
        scheduler.start()
        try:
            while True:
                time.sleep(3600)  # main thread idle; signals handle shutdown
        finally:
            scheduler.stop()
```

Live thread body:

```python
while not self._stop.is_set():
    self._watcher._douyin_live.run_once(creator_id=...)
    self._watcher._bilibili_live.run_once(creator_id=...)
    self._post_pool.drain_pending(..., limit=claim_limit)  # submit only, no wait
    self._stop.wait(timeout=live_poll_interval)
```

Slow thread body: existing vod/archive/dynamic logic with `stop.wait(interval)`.

- [ ] **Step 3: Run tests + full suite**

Run: `pytest tests/unit/test_live_scheduler.py tests/unit/test_monitor_watcher.py -v`

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(monitor): isolate live tick from VOD and post-process"
```

---

### Task 3: Enqueue on finalize without waiting for drain

**Files:**
- Modify: `src/media2text/core/live/recording.py` (no change if already enqueue-only)
- Modify: `src/media2text/core/live/post_process_pool.py` — hook `PostProcessJobRepo.claim` from live thread

Verify: after finalize, job appears as `pending` and pool picks it up within `post_process_poll_interval_sec` without blocking live thread.

- [ ] **Step 1: Integration test with fake job**

- [ ] **Step 2: Commit if any wiring fix needed**

---

## P1 — Wall-clock offline + notifications (G3/G4)

### Task 4: Config + session columns

**Files:**
- Modify: `src/media2text/core/config.py`
- Modify: `src/media2text/core/storage/db.py`
- Modify: `src/media2text/core/storage/models.py`
- Modify: `src/media2text/core/storage/repos.py`
- Test: `tests/unit/test_config.py`, `tests/unit/test_storage.py`

New fields:

```python
class LiveConfig(BaseModel):
    offline_confirm_sec: int = 45  # replaces poll-count as primary
    live_poll_interval_sec: int = 10
    post_process_max_parallel: int = 0  # 0 = auto
    post_process_queue_warn_depth: int = 5
    scan_concurrency: int = 4
```

Session columns: `first_seen_live_at`, `offline_since_at`, `recording_started_at`.

Migration in `db.py` `_migrate_live_sessions_v3`.

- [ ] Implement + tests + commit

---

### Task 5: Wall-clock offline in LiveRecordingCore

**Files:**
- Modify: `src/media2text/core/live/recording.py`
- Test: `tests/unit/test_offline_wall_clock.py`

Logic replace streak block:

```python
if still_live:
    self._sessions.clear_offline_since(row.id)
    continue

if self._recording_age_sec(row.started_at) < min_offline:
    continue

offline_since = self._sessions.get_offline_since(row.id)
now = datetime.now(timezone.utc)
if offline_since is None:
    self._sessions.set_offline_since(row.id, now.isoformat())
    self._emit_live_ended(creator, row)
    continue

elapsed = (now - parse_iso(offline_since)).total_seconds()
if elapsed >= self._cfg.live.offline_confirm_sec:
    meta = self._finalize_recording(...)
```

- [ ] Tests: first offline emits once; finalize after confirm_sec; live resume clears offline_since
- [ ] Commit

---

### Task 6: New notify kinds

**Files:**
- Modify: `src/media2text/core/notify/events.py`
- Modify: `src/media2text/core/live/post_process.py` — emit `SUMMARIZE_COMPLETED`
- Modify: `config.example.yaml` — document `notify.events.*` if gated

- [ ] Commit

---

## P2 — Pipeline events + CLI (G7/G8)

### Task 7: PipelineEventRepo

**Files:**
- Create: `src/media2text/core/live/pipeline_events.py`
- Modify: `src/media2text/core/storage/db.py` (CREATE TABLE)
- Test: `tests/unit/test_pipeline_events.py`

Helper:

```python
def emit_event(conn, *, session_id: str, stage: str, status: str, job_id: str | None = None, detail: dict | None = None) -> str:
    """Insert started; on complete/fail update ended_at + duration_ms."""
```

Instrument:
- `recording.py`: detected_live, stream_resolve, recording, remux
- `post_process.py`: transcribe, summarize, cloud_upload

- [ ] Commit

---

### Task 8: `live status` CLI

**Files:**
- Create: `src/media2text/cli/live.py`
- Modify: `src/media2text/cli/main.py`
- Test: `tests/unit/test_live_status_cli.py`

Commands:

```python
@app.command("status")
def status_cmd(creator: str | None = None, json_out: bool = False): ...

@app.command("timeline")
def timeline_cmd(session_id: str, json_out: bool = False): ...

@app.command("stats")
def stats_cmd(days: int = 7, json_out: bool = False): ...
```

JSON shape (status):

```json
{
  "ok": true,
  "active_recordings": [{"session_id", "creator", "started_at", "duration_sec", "offline_since_at"}],
  "pending_jobs": [{"job_id", "stage", "status", "queued_sec"}],
  "post_process_pool": {"max_workers", "queue_depth"}
}
```

- [ ] Commit

---

## P3 — Parallel scan + adaptive workers

### Task 9: Parallel scan_and_start

**Files:**
- Modify: `src/media2text/core/live/recording.py`
- Test: `tests/unit/test_live_recording_core.py`

Use `ThreadPoolExecutor(max_workers=cfg.live.scan_concurrency)` for creators **without** active session. Aggregate errors same as today.

- [ ] Commit

---

### Task 10: Adaptive post_process_max_parallel

**Files:**
- Modify: `src/media2text/core/live/post_process_pool.py`
- Modify: `src/media2text/core/config.py`

```python
def resolve_post_process_workers(cfg: AppConfig) -> int:
    n = cfg.live.post_process_max_parallel
    if n > 0:
        return n
    return min(2, max(1, (os.cpu_count() or 2) // 2))
```

- [ ] Commit

---

### Task 11: Docs

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `config.example.yaml`

Document: thread model, new CLI, SLA tuning (`live_poll_interval_sec`, `offline_confirm_sec`), log events to grep.

- [ ] Commit

---

## Verification checklist (manual)

验收报告：[2026-06-03-live-pipeline-v2-acceptance.md](../verification/2026-06-03-live-pipeline-v2-acceptance.md)（2026-06-03）

1. [x] Live tick 在 post-process 期间仍 ~poll 间隔 — **通过**（配置 20s，stdout 代理 p50≈22s；非 10s 专项）
2. [ ] 自然下播 — `live_ended` ≤5s；`recording_completed` ≤ confirm+remux — **延后**（本场为守护重启收尾）
3. [x] 双主播重叠录制 + 后处理不拖慢 live poll — **通过**
4. [x] `live status --json` — **通过**
5. [x] `live timeline` + `live stats` — **通过**（两场 remux→transcribe→summarize→cloud_upload 全完成，2026-06-03 12:30 UTC）

---

## Self-review (spec coverage)

| Spec requirement | Task |
|------------------|------|
| G1 30s detect→record | P0 + P3 parallel scan + poll 10s |
| G2 live_started immediate | Task 5/7 events |
| G3 live_ended immediate | Task 5 |
| G4 finalize ≤60s | Task 5 offline_confirm_sec |
| G5 isolation | Task 1–2 |
| G6 adaptive parallel | Task 10 |
| G7 traceability | Task 7–8 |
| G8 stats | Task 8 stats command |

No placeholders remain.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-06-03-live-pipeline-v2.md`.

**Two execution options:**

1. **Subagent-Driven** — fresh subagent per task, review between tasks  
2. **Inline Execution** — implement P0→P3 in this session with checkpoints

Which approach do you prefer?

---

## Decisions to confirm (from /plan-eng-review 2026-06-03)

| ID | Topic | Recommendation | Status |
|----|-------|----------------|--------|
| D1 | SQLite: per-thread `open_db()` vs single shared connection | Per-thread / per-job connection | **accepted** 2026-06-03 |
| D2 | PostProcessPool DB 边界 | 可写 transcribe/upload；禁止改 recording/ffmpeg_pid | **accepted** 2026-06-03 |
| D3 | G3 wording | 首次**检测到** offline 后 ≤5s | **accepted** 2026-06-03 |
| D4 | P0 ship without P1? | Yes — G5 only; G3/G4 in P1 + release note | **accepted** 2026-06-03 |
| D5 | `max_creators_per_vod_tick` default | `config.example.yaml` **0 → 2** | **accepted** 2026-06-03 |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | D1–D5 accepted; ready for P0 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | N/A (CLI JSON only) |
| DX Review | `/plan-devex-review` | Developer experience | 0 | — | not run |

- **UNRESOLVED:** 0
- **VERDICT:** Eng review CLEARED — D1–D5 locked in spec v1.2; start P0 implementation.
