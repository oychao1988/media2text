# media2text — Douyin-First CLI Design Spec

**Status:** Approved (brainstorming + CEO review 2026-05-20)  
**Date:** 2026-05-20  
**Scope:** MVP for personal local CLI, Agent-operable, Douyin live recording first, then VOD + transcribe  
**CEO review mode:** SELECTIVE EXPANSION — accepted: doctor, adapter v1 + fixtures, agent manifest, live process governance

---

## 1. Summary

`media2text` is a command-line tool that:

1. Logs into Douyin via browser/QR and persists sessions locally.
2. Tracks creator accounts (by profile/share link), syncs video catalogs, and incrementally downloads new posts.
3. Watches followed creators for live streams and records video with ffmpeg when they go live.
4. Transcribes downloaded or recorded video to structured text (Markdown + JSON).

Implementation is **self-developed**, with patterns borrowed from mature open-source projects (not vendored as dependencies for core logic). Bilibili support is **phase 2**.

---

## 2. Goals and Non-Goals

### Goals (MVP)

| ID | Goal |
|----|------|
| G1 | Agent-friendly CLI: stable subcommands, `--json` stdout, documented exit codes |
| G2 | Douyin login via Playwright (QR / browser), session reuse |
| G3 | Creator registry: add by URL/share link → stable `sec_uid` |
| G4 | Catalog sync with SQLite deduplication by `aweme_id` |
| G5 | Incremental VOD download (watermark-free video when available) |
| G6 | Live watch daemon: poll → record video only → stop on stream end |
| G7 | Pluggable transcription: default `faster-whisper`, optional cloud via config |
| G8 | Pipeline: `sync → download → transcribe` for a creator |

### Non-Goals (MVP)

- Bilibili or other platforms (phase 2)
- Web UI, multi-tenant server, public API hosting
- Danmaku capture, live chat, or rich live metadata
- Auto-publish, video editing, or upload workflows
- Commercial-scale crawling or bypassing platform protections beyond personal session use

### Success Criteria

**MVP gate (live-first):**

- `media2text doctor --json` reports ready (ffmpeg, playwright, valid session).
- Register a creator with `creator add`, enable `creator monitor`, run `monitor watch --daemon`, and receive a completed `.mp4` when the stream ends.
- Stale/crashed recordings are marked `failed` in `live_sessions`; daemon recovers without duplicate ffmpeg for the same room.

**MVP gate (VOD + transcribe, phase 2 within MVP):**

- `pipeline run --creator <id> --json` returns new downloads plus transcript paths.
- Re-running sync/download is idempotent (no duplicate files for same `aweme_id`).
- Session expiry surfaces `auth_required: true` in JSON for Agents to call `auth login`.
- Each creator workspace exposes `agent-manifest.json` for Agent discovery without directory scans.

---

## 3. Reference Projects (Patterns Only)

| Project | Use as reference for |
|---------|----------------------|
| [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) | Profile batch flow, SQLite dedup, retries, browser fallback |
| [ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder) | Live URL forms, stream URL resolution, ffmpeg recording |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Fallback single-URL extraction when custom adapter fails |
| faster-whisper / cloud APIs | Transcription backends |

**License note:** Core Douyin adapter code is written in-repo; no copy-paste of GPL bundles. MIT-style reference implementations inform API shapes and error handling only.

---

## 4. Architecture

### 4.1 High-Level

```
CLI (Typer)
  → auth/session store (Playwright + encrypted cookie jar)
  → creator registry + SQLite
  → douyin adapter (list / download / live status / stream URL)
  → download worker (queue + ffmpeg when needed)
  → monitor watcher (live poll + VOD pipeline tick; ffmpeg child processes)
  → transcribe plugins (whisper | cloud)
  → pipeline orchestrator
```

### 4.2 Repository Layout

```
media2text/
  pyproject.toml
  config.example.yaml
  src/media2text/
    cli/                    # entry: media2text
    core/
      platform/
        douyin/
          auth.py           # login, session load/save
          resolver.py       # URL → sec_uid, live room id
          catalog.py        # list aweme / pagination
          download.py       # fetch media URLs, write files
          live.py           # is_live, stream URL, record lifecycle
          adapter.py        # DouyinAdapterV1 facade + fallback to yt-dlp
          fixtures/         # recorded HTTP/HTML samples for CI (no live network)
      transcribe/
        base.py
        whisper.py
        cloud_openai.py     # example cloud backend
      storage/
        db.py               # SQLite schema + migrations
        models.py
      pipeline/
        runner.py
    schemas/                # Pydantic models for --json output
  data/                     # default workspace (gitignored)
    sessions/
    media2text.db
    creators/{sec_uid}/videos/
    creators/{sec_uid}/live/
    transcripts/
    creators/{sec_uid}/agent-manifest.json   # Agent index (paths + statuses)
  docs/superpowers/specs/
```

### 4.3 Data Model (SQLite)

**`creators`**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | internal uuid |
| platform | TEXT | `douyin` |
| sec_uid | TEXT UNIQUE | stable creator id |
| display_name | TEXT | optional |
| unique_id | TEXT | optional |
| avatar_url | TEXT | optional |
| profile_url | TEXT | original add URL |
| profile_synced_at | TEXT | optional ISO8601 |
| monitor_enabled | INTEGER | 1 = included in `monitor watch` (live + VOD) |
| watch_live | INTEGER | legacy; migrated to `monitor_enabled` |
| created_at | TEXT ISO8601 | |

**`awemes`**

| Column | Type | Notes |
|--------|------|-------|
| aweme_id | TEXT PK | platform video id |
| creator_id | TEXT FK | |
| title | TEXT | |
| create_time | INTEGER | unix |
| media_type | TEXT | `video` \| `image` (MVP: video priority) |
| sync_status | TEXT | `listed` \| `downloaded` \| `failed` |
| local_path | TEXT | nullable |
| transcribe_status | TEXT | `pending` \| `done` \| `failed` |
| transcript_path | TEXT | nullable |
| updated_at | TEXT | |

**`live_sessions`**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| creator_id | TEXT FK | |
| room_id | TEXT | |
| ffmpeg_pid | INTEGER | nullable; set while recording |
| started_at | TEXT | |
| ended_at | TEXT | nullable |
| local_path | TEXT | nullable; final mp4 after remux |
| temp_path | TEXT | nullable; in-progress flv/ts |
| status | TEXT | `recording` \| `remuxing` \| `completed` \| `failed` |
| error | TEXT | nullable; e.g. `stale_recording` |

**`jobs`** (optional MVP table for pipeline progress)

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| type | TEXT | `sync` \| `download` \| `transcribe` \| `pipeline` |
| payload_json | TEXT | |
| status | TEXT | `running` \| `done` \| `failed` |
| error | TEXT | nullable |

---

## 5. CLI Commands

All commands accept `--json` for machine-readable output on stdout; human-readable logs go to stderr.

| Command | Description |
|---------|-------------|
| `media2text auth login --platform douyin` | Open browser, complete login, save session under `data/sessions/` |
| `media2text auth status [--platform douyin]` | Report session validity |
| `media2text creator add <url>` | Resolve and register creator (default `monitor_enabled=0`) |
| `media2text creator list` | List registered creators |
| `media2text creator show <id>` | Profile, monitor flag, aweme counts |
| `media2text creator refresh <id>` | Refresh profile metadata |
| `media2text creator monitor <id> [--off]` | Enable/disable unified monitoring |
| `media2text creator remove <id> [--delete-media]` | Remove creator; optional `data/creators/{sec_uid}/` cleanup |
| `media2text creator sync <id>` | Fetch catalog; upsert `awemes` |
| `media2text download run [--creator id] [--limit N]` | Download pending awemes (no `--creator` → `monitor_enabled=1` only) |
| `media2text monitor watch [--daemon] [--creator id]` | Poll live + periodic VOD pipeline for monitored creators |
| `media2text transcribe run <path\|dir>` | Run transcription (`whisper` or `openai` per config) |
| `media2text pipeline run --creator <id>` | sync → download → transcribe |
| `media2text doctor [--json]` | Check ffmpeg, playwright, session, disk; exit non-zero if not ready |
| `media2text version` | Version string |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Auth required / session expired |
| 3 | Resolve or parse failure (bad URL, blocked) |
| 4 | Partial success (e.g. some downloads failed) |

### JSON Response Shape (example)

```json
{
  "ok": true,
  "command": "creator sync",
  "creator_id": "…",
  "new_count": 12,
  "total_listed": 340,
  "auth_required": false,
  "platform_changed": false
}
```

---

## 6. Douyin Adapter Behavior

### 6.1 Authentication

- Launch headless or headed Chromium via Playwright.
- Navigate to Douyin; user completes QR or logged-in state.
- Persist: cookies + minimal storage state to `data/sessions/douyin.json` (permissions `0600`).
- Persist Playwright `storage_state` to `data/sessions/douyin.json` (`0600`).
- **HTTP primary path (eng review):** export cookies to an `httpx.Client` cookie jar for `resolve_creator`, `is_live`, `list_awemes`, `resolve_download_url`, `resolve_stream_url`.
- **Fallback:** on `ParseFailed` / empty body / signature failure, retry the same operation via Playwright request context or page scrape (same session file).
- On `401`/`403` or known “not login” signals, set `auth_required` and exit code `2`.

### 6.2 Creator Resolution

Supported inputs (MVP):

- `https://v.douyin.com/…` (short link)
- `https://www.douyin.com/user/…`
- `https://live.douyin.com/…` (resolve to anchor `sec_uid` for watch list)
- Raw `sec_uid` if passed explicitly via future flag

Resolver caches `sec_uid` on `creators` row. Short links: follow redirects with session.

### 6.3 Catalog Sync

- Paginate creator post list until empty or configurable max pages.
- Store metadata only in sync phase (no binary download).
- Dedupe by `aweme_id`; update `title`, `create_time` if changed.
- On API failure: retry with exponential backoff; then Playwright page scrape fallback (parse embedded JSON/bootstrap).

### 6.4 VOD Download

- For each `aweme` with `sync_status=listed`, resolve play URL(s).
- Write to `data/creators/{sec_uid}/videos/{aweme_id}.mp4` (or `.mp4` + sidecar metadata json).
- Concurrency from `config.download_concurrency` (default 3).
- Mark `downloaded` or `failed` with error message in job log.

### 6.5 Unified Monitor (`monitor watch`)

- **收录 vs 监控**：`creator add` 仅登记；`creator monitor` 设置 `monitor_enabled=1` 后，`monitor watch` 才轮询该创作者。
- Live leg: on `monitor.live_poll_interval_sec` (default 60), check each creator with `monitor_enabled=1`.
- If live: resolve stream URL (flv/hls) via **httpx** (cookies from session); on `ParseFailed` / `PlatformChanged`, retry via Playwright page context.
- **Recording strategy (eng review):** ffmpeg writes a **temporary stream file** (`.flv` or `.ts`, `-c copy`) under `data/creators/{sec_uid}/live/.tmp/{session_id}/`; on stream end, remux to final `data/creators/{sec_uid}/live/{timestamp}.mp4`, then delete temp dir. Avoids corrupt single `.mp4` on crash mid-stream.
- Track row in `live_sessions` with `status=recording`, `ffmpeg_pid`, `room_id`, `temp_path`.
- On stream end or poll sees offline: SIGTERM ffmpeg → wait `ffmpeg_stop_timeout_sec` → SIGKILL → run remux step → `status=completed` (or `failed` if remux fails, keep temp for manual recovery).
- **Process governance (MVP):**
  - `monitor watch --daemon` acquires a workspace lock file (`data/.monitor-watch.lock`); second instance exits with code `1` and JSON `already_running: true`.
  - At daemon start, any `live_sessions` with `status=recording` and dead PID → mark `failed` with reason `stale_recording`.
  - At most one active ffmpeg per `room_id`; re-poll while live does not spawn duplicates.
- Optional config: `live.transcribe_on_complete: true` → after remux, run Whisper on the finished `.mp4` and refresh manifest.
- VOD leg: on `monitor.vod_poll_interval_sec`, run `sync → download → transcribe` per monitored creator (respect `max_creators_per_vod_tick`).
- **No** danmaku, gifts, or chat files in MVP.

### 6.7 Agent Manifest

After any download, live completion, or transcribe, refresh `data/creators/{sec_uid}/agent-manifest.json`:

```json
{
  "sec_uid": "...",
  "updated_at": "ISO8601",
  "items": [
    {
      "id": "aweme_id or live_session_id",
      "type": "vod|live",
      "title": "...",
      "media_path": "...",
      "transcript_path": null,
      "status": "downloaded|transcribed|failed"
    }
  ]
}
```

Agents read this file instead of scanning directories.

### 6.8 DouyinAdapterV1 Contract

- All Douyin HTTP/HTML parsing lives behind `DouyinAdapterV1` with explicit methods: `resolve_creator`, `list_awemes`, `resolve_download_url`, `is_live`, `resolve_stream_url`.
- Adapter errors map to: `AuthRequired`, `RateLimited`, `ParseFailed`, `PlatformChanged` (signature/API drift).
- Exit code `3` for resolve/parse; include `platform_changed: true` in JSON when heuristics detect HTML/JSON shape drift.
- CI tests use fixtures under `platform/douyin/fixtures/` only (no live Douyin in CI).

### 6.6 Fallback

- If custom resolver/download fails for a single URL, invoke `yt-dlp` subprocess with session cookies file export (best-effort).

---

## 7. Transcription

### 7.1 Plugin Interface

```python
class TranscribeBackend(Protocol):
    def transcribe(self, media_path: Path, *, language: str | None) -> TranscriptResult: ...
```

`TranscriptResult`: `text`, `segments[{start,end,text}]`, `engine`, `model`.

### 7.2 Backends

| Engine | Config key | Notes |
|--------|------------|-------|
| whisper | `transcribe.engine: whisper` | faster-whisper; `model`, `device` |
| openai | `transcribe.engine: openai` | API key from env |

### 7.3 Outputs

Per input `foo.mp4`:

- `foo.transcript.json` — segments + metadata
- `foo.transcript.md` — readable paragraphs with optional timestamps

Update `awemes.transcribe_status` / `transcript_path` when run via pipeline.

---

## 8. Configuration

`config.yaml` in workspace root (or `MEDIA2TEXT_CONFIG` path):

```yaml
workspace: ./data

platforms:
  douyin:
    poll_interval_sec: 60
    download_concurrency: 3
    max_sync_pages: 0          # 0 = no limit

live:
  transcribe_on_complete: false
  ffmpeg_path: ffmpeg          # or absolute path
  ffmpeg_stop_timeout_sec: 30
  temp_format: flv             # flv | ts — intermediate while recording

transcribe:
  engine: whisper
  language: zh
  whisper:
    model: medium
    device: auto
  openai:
    api_key_env: OPENAI_API_KEY
    model: whisper-1
```

---

## 9. Pipeline

`pipeline run --creator <id>`:

1. `creator sync` — list new awemes
2. `download run --creator <id>` — fetch pending
3. `transcribe` on all `downloaded` without transcript (or `transcribe_status=pending`)

Emit final JSON: counts per stage, paths, failures array.

---

## 10. Error Handling and Operations

- **Rate limits / blocks:** backoff + log; surface in JSON `errors[]`; do not crash daemon.
- **Disk space:** pre-check optional; fail download with clear message.
- **ffmpeg missing:** `doctor` fails before pipeline/live; exit 1 with install hint.
- **Adapter drift:** surface `platform_changed: true`; log snippet hash of response for debugging (never log cookies).
- **Partial download:** resume via temp file + atomic rename where supported.

---

## 11. Security and Compliance

- Sessions and DB live only under user-configured `workspace`; never logged to stdout in `--json` mode.
- Tool is for **personal archival** of creators the user follows; user responsible for platform ToS.
- No bundled credentials; cloud keys via environment variables only.

---

## 12. Testing Strategy

| Layer | Tests |
|-------|-------|
| resolver | Unit tests with recorded HTTP fixtures (no live network in CI) |
| storage | SQLite migration + CRUD |
| transcribe | Mock backend; one integration test with tiny sample wav |
| cli | Typer runner invoke with temp workspace |
| live | Manual / marked integration (requires live or mocked stream URL) |

CI: lint (ruff), typecheck (pyright/mypy), unit tests without network.

---

## 13. Implementation Phases (live-first, per CEO review)

| Phase | Deliverable | MVP gate |
|-------|-------------|----------|
| P0 | Scaffold, config, SQLite, `auth login/status`, **`doctor`** | doctor passes |
| P1 | `creator add/list`, resolver, **`monitor watch`** + process governance | records one live to mp4 |
| P2 | `creator sync`, `download run`, `agent-manifest.json` refresh | incremental VOD download |
| P3 | `transcribe` (whisper) + manifest update | transcript json/md |
| P4 | `pipeline run`, exit codes, Agent README | full vod pipeline |
| P5 | Hardening: fixture suite for DouyinAdapterV1, stale-session tests | CI green offline |
| P6 | Bilibili adapter (separate spec) | — |

**Rationale:** Live stream URL resolution and daemon stability are the highest-risk Douyin surfaces; proving them first de-risks the product. VOD sync reuses the same auth/resolver stack once live works.

---

## 14. Agent Integration Notes

- Prefer `media2text <cmd> --json` and parse stdout only.
- On `auth_required: true`, run `auth login` interactively (user must complete QR).
- Store `creator_id` from `creator add` response for subsequent calls.
- Use `pipeline run` for batch; use `monitor watch --daemon` as long-running process with log file tailing.
- On `platform_changed: true`, adapter parsers detected API drift — file an issue or update fixtures; exit code `3`.

---

## 15. Open Questions (Post-MVP)

- Image/carousel aweme support (download as zip vs skip)
- MCP server wrapper exposing same operations as tools
- Session encryption at rest (beyond `0600` permissions)
- Optional metrics file (`data/metrics.jsonl`) for daemon observability

---

## 16. CEO Review Summary (2026-05-20)

### Verdict

**APPROVED with amendments.** Scope is coherent for a personal Agent CLI. Primary risk is **Douyin adapter churn**, not architecture. Live-first phase order matches user priority.

### What already exists

- Greenfield repo; only design spec + Claude config. No code to reuse.

### NOT in scope (confirmed)

- Bilibili (P6), Web UI, danmaku, commercial crawling, MCP (post-MVP).

### Dream state delta (12 months)

Ideal: searchable archive of every followed creator (VOD + live) with transcripts and stable Agent API. This spec reaches ~40% of that (local files + manifest + CLI). Gap: full-text search index, cross-creator query, Bilibili parity.

### Critical gaps addressed in this revision

| Gap | Fix |
|-----|-----|
| Daemon double-start | workspace lock file |
| Zombie ffmpeg | PID tracking + stale session cleanup |
| Agent discovery | `agent-manifest.json` |
| Silent environment failures | `doctor` in MVP |
| Platform API drift | `DouyinAdapterV1` + fixtures + `platform_changed` |

### Deferred cherry-picks (user: skip/defer)

- None from offered set; all four expansions accepted.

### Section scores (findings → fixes)

| Section | Issues | Action |
|---------|--------|--------|
| Architecture | Missing live lock + adapter boundary | Added §6.5, §6.8 |
| Errors | Unrescued ffmpeg/playwright failures | doctor + stale recording rules |
| Security | Cookie leakage via logs/subprocess | Explicit in §10/§6.8 |
| Data/UX | Pagination error vs empty | Adapter contract (implement in P2) |
| Tests | No offline Douyin CI | fixtures/ in P5 |
| Perf | Whisper backlog on long live | Note: queue transcribe jobs (P3) |
| Observability | Thin | manifest + structured stderr logs |
| Deploy | N/A local CLI | lock file + daemon recovery |
| Future | Adapter maintenance | AdapterV1 versioning |
| Design UI | N/A CLI-only | Skipped |

---

## Appendix: Decisions Log

| Decision | Choice |
|----------|--------|
| Interface | Personal CLI, Agent-oriented |
| Platform MVP | Douyin (B站 phase 2) |
| Login | Playwright QR/browser, local session |
| Transcription | Pluggable; default faster-whisper |
| Implementation | Self-developed; reference OSS patterns |
| Live scope | Video recording only |
| Architecture | Thin orchestrator (方案 1) |
| CEO review | SELECTIVE EXPANSION; live-first phasing |
| MVP expansions | doctor, AdapterV1+fixtures, agent-manifest, live process governance |
| Eng review | httpx primary + Playwright fallback; live flv/ts → remux mp4 |
| Tech stack | Python 3.12, Typer, Pydantic v2, httpx, Playwright, SQLite WAL, faster-whisper, structlog, pytest |

---

## 17. Eng Review Summary (2026-05-20)

### Verdict

**APPROVED for implementation** with recorded decisions. Spec is implementable live-first. Highest engineering risk remains **DouyinAdapterV1** maintenance, not CLI shape.

### Step 0 — Scope

| Check | Result |
|-------|--------|
| Existing code to reuse | None (greenfield) |
| Minimum path to live MVP | P0 auth+doctor → P1 creator+live (aligned) |
| File/class count | ~12 modules in `src/media2text/` — acceptable for stated goals |
| Distribution | Add `pyproject.toml` `[project.scripts] media2text = ...`; document `uv pip install -e .` in README (P0) |
| Completeness | Prefer full error taxonomy + fixture CI (P5) over shortcuts |

### Architecture (decisions locked)

```
                    ┌─────────────┐
                    │  Typer CLI  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   ┌──────────┐    ┌──────────────┐   ┌─────────────┐
   │  doctor  │    │ live daemon  │   │ vod/pipeline│
   └──────────┘    │ (poll loop)  │   └──────┬──────┘
                   └──────┬───────┘          │
                          │                  │
                   ┌──────▼──────────────────▼──────┐
                   │     DouyinAdapterV1            │
                   │  httpx (+cookies) → PW fallback  │
                   └──────┬─────────────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌─────────┐ ┌─────────┐ ┌──────────┐
        │ SQLite  │ │ ffmpeg  │ │ yt-dlp   │
        │  WAL    │ │ subprocess│ │ fallback │
        └─────────┘ └─────────┘ └──────────┘
```

**User decisions (AskUserQuestion):**

| ID | Choice |
|----|--------|
| D1 Live recording | **flv/ts temp → remux mp4** on stream end |
| D2 HTTP stack | **httpx primary** + Playwright fallback |

**Additional eng recommendations (apply unless overridden):**

| ID | Recommendation | Rationale |
|----|----------------|-----------|
| E1 | SQLite `PRAGMA journal_mode=WAL; busy_timeout=5000` | CLI + daemon concurrent DB access |
| E2 | Single-process daemon (sync poll loop + subprocess), not threaded scraper | Simpler ffmpeg PID ownership |
| E3 | Domain exceptions: `Media2TextError` → `AuthRequired`, `RateLimited`, `ParseFailed`, `PlatformChanged`, `RecordingError` | Maps to exit codes; no bare `except Exception` |
| E4 | structlog JSON to stderr; stdout only for `--json` | Agent contract |
| E5 | `manifest` + DB updated in one `storage.transaction()` | Avoid half-written agent state |

### Error & rescue map (live path)

| Codepath | Failure | Handling | User/Agent sees |
|----------|---------|----------|-----------------|
| `is_live()` | httpx timeout | retry 3x, then PW fallback | stderr warn; continue poll |
| `is_live()` | auth expired | `AuthRequired`, exit 2 | `auth_required: true` |
| `resolve_stream_url()` | parse drift | `PlatformChanged` | `platform_changed: true`, exit 3 |
| ffmpeg record | stream 404 mid-run | mark session failed, kill pid | JSON `recording_failed` |
| ffmpeg record | process crash | stale cleanup on daemon start | `stale_recording` in DB |
| remux | ffmpeg error | `status=failed`, keep `temp_path` | path to temp in JSON |
| lock file | second daemon | exit 1 | `already_running: true` |

### Test coverage diagram (planned — implement in P1–P5)

```
CODE PATHS (P1 live)                         USER / AGENT FLOWS
[+] DouyinAdapterV1.is_live                  [+] Agent runs doctor before live
  ├── [GAP] httpx 200 live=true               ├── [GAP] [→manual] daemon records real stream
  ├── [GAP] httpx 200 live=false              └── [GAP] auth_required triggers re-login
  ├── [GAP] httpx timeout → PW fallback
  └── [GAP] PlatformChanged
[+] live.watch daemon
  ├── [GAP] acquire lock / reject duplicate
  ├── [GAP] start ffmpeg → temp flv
  ├── [GAP] stale PID cleanup on startup
  ├── [GAP] SIGTERM → remux → completed
  └── [GAP] remux failure → failed + temp kept
[+] creator.add / resolver
  ├── [GAP] short URL redirect
  └── [GAP] live URL → sec_uid

COVERAGE: 0/N (pre-code) — P5 target: adapter fixtures ≥80% branch coverage
```

**P1 minimum tests before calling live MVP done:**

- Unit: lock file, stale session cleanup, cookie load into httpx
- Fixture: `is_live` true/false JSON, `resolve_stream_url` sample
- Integration (marked `@pytest.mark.live`): one real short live test locally

### Performance notes

| Area | Note |
|------|------|
| Poll interval 60s | Acceptable; expose config; document missed stream start ≤60s |
| Whisper on 3h live | Run transcribe async job queue; do not block daemon (P3) |
| httpx connection pool | One client per process, reuse |
| Download concurrency 3 | OK; add per-domain rate limit backoff |

### Parallelization (implementation)

| Lane | Phases | Depends on |
|------|--------|------------|
| A | P0 scaffold + storage + exceptions | — |
| B | P1 adapter live + daemon (after A) | P0 |
| C | P2 vod download (after A) | P0; shares adapter with B |
| D | P3 transcribe (after A) | P0 |
| E | P4 pipeline (after B,C,D) | B,C,D |

**Parallel after P0:** Lane B + C + D in separate worktrees possible (touch different modules). Lane E waits for all.

### NOT in scope (eng)

- Async/await rewrite of entire CLI (unnecessary innovation token)
- Embedded job queue (Redis/Celery)
- Packaging .dmg/.exe (post-MVP; document `pip install -e .` first)

### What already exists

- None.

### Failure modes — critical gaps (pre-implementation)

| Codepath | Failure | Test? | Handled? | Silent? |
|----------|---------|-------|----------|---------|
| remux | disk full | GAP | GAP | would be silent without check |
| cookie export | empty jar | GAP | partial | fix in P0 doctor |
| poll during sleep | laptop suspend | GAP | GAP | document OS limitation |

**Action:** P0 `doctor` checks disk free > N GB; P1 remux checks output file size > 0.

### Completion summary

```
+====================================================================+
|            PLAN ENG REVIEW — COMPLETION SUMMARY                     |
+====================================================================+
| Step 0               | Scope accepted (live-first)                   |
| Architecture         | 5 recommendations + 2 user decisions locked   |
| Code quality         | exception taxonomy, module boundaries OK      |
| Test review          | diagram produced, 0/N (pre-code)              |
| Performance          | 3 notes (poll, whisper, rate limit)           |
| NOT in scope         | written                                       |
| What already exists  | written                                       |
| Failure modes        | 3 critical gaps flagged → spec fixes          |
| Outside voice        | skipped                                       |
| Parallelization      | 5 lanes after P0                              |
| VERDICT              | CLEARED for implementation planning           |
+====================================================================+
```
