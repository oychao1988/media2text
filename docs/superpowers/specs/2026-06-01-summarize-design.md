# media2text — LLM Transcript Summarize Design Spec

**Status:** Approved (brainstorming 2026-06-01; LLM provider confirmed same day)  
**Date:** 2026-06-01  
**Scope:** Post-transcription LLM summarization — per-file and merged live sessions  
**Depends on:** Existing `.transcript.json` / `.transcript.md` sidecars; OpenAI-compatible Chat API (`".[transcribe-cloud]"`)

**LLM provider (confirmed):** NVIDIA integrate API + `deepseek-ai/deepseek-v4-pro`. Summarize LLM is **independent** of `transcribe.engine` (e.g. Deepgram 转写 + NVIDIA 总结).

---

## 1. Summary

Add a **`summarize`** CLI module that reads completed transcripts and produces structured summary documents via an LLM (OpenAI-compatible API). Supports:

1. **Per-media summaries** — one `.summary.md` (+ optional `.summary.json`) beside each transcript.
2. **Profile-based prompts** — auto-select `live_market_recap` vs `vod_highlights` vs `neutral_minutes`.
3. **Split live recordings** — when one broadcast is recorded as multiple MP4s (stream drop + resume), **auto-detect merge candidates** and expose them as `suggested_groups`; user confirms before `summarize merge` runs.

**Product decision (confirmed):** merge behavior **B** — detect and suggest groups in JSON output; **no silent auto-merge** by default.

---

## 2. Goals and Non-Goals

### Goals

| ID | Goal |
|----|------|
| G1 | Agent-friendly CLI: `summarize run`, `summarize merge`, `--json`, stable exit codes |
| G2 | Input from `.transcript.json` (segments + timestamps), not raw MP4 |
| G3 | Long-text handling: chunk → partial summaries → merge (map-reduce) |
| G4 | Profile `auto`: live → `live_market_recap`, vod → `vod_highlights`, dynamic text → `neutral_minutes` |
| G5 | Split-session detection: same creator + same day + gap ≤ threshold → `suggested_groups` |
| G6 | Explicit `summarize merge` after user/agent confirms grouping |
| G7 | Compliance disclaimer header on every summary (fixed text, not LLM-generated) |
| G8 | Refresh `agent-manifest.json` with `summary_path`; optional cloud upload of summary sidecars |

### Non-Goals (v1)

- Multi-vendor LLM plugin matrix (Anthropic, Ollama, etc.) — v1 is OpenAI-compatible only
- Cross-creator weekly digest / RAG chat over summaries
- LLM-based “is this the same broadcast?” — use time + `room_id` heuristics only
- Cross-midnight merge (23:50 + 00:10) — defer to v2 (`merge_cross_midnight`)
- Replacing or extending `archive search` with summary FTS — phase 2
- Investment advice generation — summaries **organize stated content only**

### Success Criteria

- `media2text summarize run data/creators/.../live/xxx.mp4 --json` writes `xxx.summary.md` when `xxx.transcript.json` exists.
- `media2text summarize run --creator <id> --json` returns `suggested_groups` when two live sessions on the same day are within `merge_gap_minutes`.
- `media2text summarize merge --sessions id1,id2 --json` writes `{date}_merged.summary.md` with deduplicated cross-part content.
- Re-run without `--force` skips existing summary files (idempotent).
- Unit tests mock LLM; no live API in default CI.

---

## 3. Architecture

### 3.1 High-Level

```
CLI summarize/
  → read transcript sidecar (.transcript.json | dynamics/content.md)
  → resolve profile (auto | override)
  → chunker (by time / char budget)
  → OpenAISummarizeBackend (Chat Completions)
  → write summary sidecars (.summary.md, .summary.json)
  → group detector (live_sessions DB) → suggested_groups
  → merge orchestrator (multi-part → single merged summary)
  → refresh_manifest (+ optional index_transcript_safe phase 2)
```

### 3.2 Repository Layout (new)

```
src/media2text/
  cli/summarize.py
  core/summarize/
    __init__.py
    base.py              # SummaryResult, profile names
    reader.py            # load transcript.json, content.md
    chunker.py           # segment-aware chunking
    llm_backend.py       # Chat Completions client (OpenAI-compatible)
    prompts.py           # built-in profile templates
    writer.py            # write .summary.md / .summary.json
    grouper.py           # suggested_groups heuristics
    merger.py            # multi-part merge pipeline
    factory.py           # create backend from config
```

### 3.3 Pipeline Position

Existing live finalize order (unchanged unless config enables summarize):

```text
remux → notify → [transcribe] → [cloud upload] → refresh_manifest
```

When `summarize.on_transcribe_complete: true`:

```text
remux → notify → transcribe → summarize run (single file) → [suggest merge groups in JSON only] → cloud upload → refresh_manifest
```

`summarize` failures must **not** block cloud upload or mark live session failed (same pattern as transcribe skip).

---

## 4. File Conventions

### 4.1 Per-media sidecars

| File | Description |
|------|-------------|
| `{basename}.transcript.json` | Existing input |
| `{basename}.summary.md` | Human-readable summary (primary deliverable) |
| `{basename}.summary.json` | Metadata for Agents (v1); parsed `sections` in v2 |

### 4.2 Merged live summary

For sessions merged on date `2026-06-01`:

| File | Description |
|------|-------------|
| `live/20260601_merged.summary.md` | Combined broadcast summary |
| `live/20260601_merged.summary.json` | `sources[]`, profile, model, generated_at |

Naming: `{YYYYMMDD}_merged` in the **live/** directory of the creator workspace (UTC date of first part’s `started_at`, configurable).

### 4.3 summary.json schema (minimal)

**v1 scope:** `.summary.json` is **metadata only** (engine, model, profile, chunk count, source paths, timestamps). Structured `sections` parsed from LLM output is **deferred to v2**; v1 deliverable is `.summary.md` (markdown-first).

```json
{
  "engine": "openai",
  "model": "deepseek-ai/deepseek-v4-pro",
  "provider_base_url": "https://integrate.api.nvidia.com/v1",
  "profile": "live_market_recap",
  "source_transcript": ".../20260601T130643Z.transcript.json",
  "generated_at": "2026-06-01T15:00:00+00:00",
  "disclaimer": "个人研究档案整理，不构成投资咨询或买卖建议。",
  "chunks": 3,
  "markdown_path": ".../20260601T130643Z.summary.md"
}
```

Merged variant adds:

```json
{
  "merged": true,
  "sources": [
    {"session_id": "...", "media_path": ".../20260601T124448Z.mp4", "part": 1},
    {"session_id": "...", "media_path": ".../20260601T130643Z.mp4", "part": 2}
  ]
}
```

---

## 5. Configuration

Add to `config.example.yaml` (defaults below match **recommended deployment**: NVIDIA + DeepSeek; swap `api_key_env` / `base_url` / `model` for OpenAI direct if needed):

```yaml
summarize:
  enabled: false
  engine: openai                 # v1: OpenAI-compatible Chat Completions only
  on_transcribe_complete: false
  default_profile: auto          # auto | live_market_recap | vod_highlights | neutral_minutes
  merge_gap_minutes: 60
  merge_date_tz: UTC
  llm:
    api_key_env: NVIDIA_API_KEY
    base_url: https://integrate.api.nvidia.com/v1
    model: deepseek-ai/deepseek-v4-pro
    temperature: 0.2
    top_p: 0.95
    max_output_tokens: 16384
    thinking: false              # maps to extra_body.chat_template_kwargs.thinking
  chunk:
    max_chars: 24000             # per LLM call input budget (approx)
    minutes: 30
  merge:
    auto_merge_after_parts: false  # B: never auto-merge; only suggest
```

**Dependency:** reuse `pip install -e ".[transcribe-cloud]"` (OpenAI SDK). No new optional extra for v1.

**Env (`.env`):** `NVIDIA_API_KEY=nvapi-...` (see `.env.example`). Do **not** commit keys.

**Backend implementation (`llm_backend.py`):**

```python
extra_body = {"chat_template_kwargs": {"thinking": cfg.summarize.llm.thinking}}
# when thinking is false/absent for non-DeepSeek models, omit extra_body
```

**Verified (2026-06-01):** `deepseek-ai/deepseek-v4-pro` via `https://integrate.api.nvidia.com/v1` — OpenAI Python SDK, `thinking: false`, ~8s for short prompt.

---

## 6. Prompt Profiles

### 6.1 `live_market_recap`

For Douyin/Bilibili live transcripts. Output sections:

- 核心观点（bullet list）
- 时间窗口 / 关键日期（with segment time refs)
- 板块 / 主题（structured)
- 风险提示 / 免责声明呼应（organize only, no new advice)
- 重复表述去重说明（for merge pass)

### 6.2 `vod_highlights`

For short-form VOD. Output:

- 3–5 bullet highlights
- Optional 金句 (quoted from transcript)
- One-line topic label

### 6.3 `neutral_minutes`

For Bilibili `dynamics/*/content.md` (no video). Input is markdown body, not segments.

### 6.4 `auto` resolution

| Source | Condition | Profile |
|--------|-----------|---------|
| Live MP4 / `live_sessions` row | default | `live_market_recap` |
| Aweme / vod MP4 | default | `vod_highlights` |
| `content.md` only | `--path dynamics/.../content.md` | `neutral_minutes` |

CLI override: `--profile <name>`.

---

## 7. CLI

Register in `cli/main.py`:

```text
media2text summarize run <path> [--creator] [--profile] [--force] [--json]
media2text summarize merge (--sessions id[,id...] | --paths p[,p...] | --creator --date YYYY-MM-DD [--group-index N]) [--profile] [--force] [--json]
media2text summarize suggest (--creator <id> [--date YYYY-MM-DD] [--json])   # optional; or embed in run --json
```

### 7.1 `summarize run`

**Args:** file, directory, or `--creator` (all items with transcript, no summary yet).

**Behavior:**

1. Resolve transcript path from media path (or direct `.transcript.json`).
2. Skip if `.summary.md` exists and not `--force`.
3. Chunk + LLM + write sidecars.
4. For `--creator`: after processing, compute `suggested_groups` (see §8).
5. `refresh_manifest` for affected creators.

**JSON response:**

```json
{
  "ok": true,
  "command": "summarize run",
  "summarized": 2,
  "skipped": 1,
  "results": [
    {
      "media_path": "...",
      "summary_path": "...",
      "profile": "live_market_recap",
      "chunks": 4
    }
  ],
  "suggested_groups": [
    {
      "date": "2026-06-01",
      "creator_id": "...",
      "session_ids": ["5ed9fd0f-...", "1adc651c-..."],
      "media_paths": [".../20260601T124448Z.mp4", ".../20260601T130643Z.mp4"],
      "gap_minutes": 31,
      "room_id": "12345",
      "merge_command": "media2text summarize merge --sessions 5ed9fd0f-...,1adc651c-... --json"
    }
  ],
  "errors": []
}
```

### 7.2 `summarize merge`

**Requires explicit invocation** (decision B). Validates:

- All sessions same `creator_id`
- All have `.transcript.json` (and optionally per-part `.summary.md` — not required for merge)
- User must pass `--sessions id1,id2,...` **or** `--group-index N` when multiple `suggested_groups` exist for the same creator + date
- Bare `--creator --date` is allowed **only** when exactly one suggested group matches (otherwise exit 1 with list of groups and required flags)

**Merge LLM flow:**

1. Load all transcripts; tag segments with `part_index`.
2. Per part: if longer than chunk budget, partial summarize first.
3. Final merge call: dedupe, unified structure, preserve `(Part N, start-end)` refs.
4. Write `{date}_merged.summary.*`; refresh manifest `live_groups` entry.

**JSON response:**

```json
{
  "ok": true,
  "command": "summarize merge",
  "merged_summary_path": ".../live/20260601_merged.summary.md",
  "session_ids": ["...", "..."],
  "parts": 2
}
```

### 7.3 Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config / API key / invalid args |
| 4 | Partial failure (some files failed) |

Align with existing `cli_exit` patterns.

---

## 8. Split Live Session Grouping (Decision B)

### 8.1 Heuristic (`core/summarize/grouper.py`)

Candidate group = ordered list of `live_sessions` rows where:

1. Same `creator_id`
2. Same calendar date (per `merge_date_tz` on `started_at`)
3. Status `completed`, `local_path` and transcript sidecar exist
4. For adjacent pair (A, B) in start-time order:  
   `minutes(B.started_at - A.ended_at) <= merge_gap_minutes`
5. Optional strengthen: same non-null `room_id`

**Do not** merge if gap exceeds threshold or dates differ.

### 8.2 Suggested groups only

- `summarize.run` and `summarize suggest` populate `suggested_groups` in JSON.
- `config.summarize.merge.auto_merge_after_parts` defaults **`false`**.
- Human or Agent runs `summarize merge` when satisfied with grouping.
- If ambiguous (3+ sessions chain), return one group covering the full chain (document in tests).

### 8.3 Manifest extension

Add to `agent-manifest.json`:

```json
{
  "live": [
    {
      "id": "...",
      "summary_path": ".../20260601T130643Z.summary.md",
      ...
    }
  ],
  "live_groups": [
    {
      "date": "2026-06-01",
      "session_ids": ["...", "..."],
      "summary_path": ".../live/20260601_merged.summary.md"
    }
  ]
}
```

Per-item `summary_path` uses same sidecar detection as `transcript_path`.

---

## 9. Integrations

### 9.1 Live / pipeline hooks

- `summarize.on_transcribe_complete` mirrors `live.transcribe_on_complete` (same hook pattern; config key under `summarize`, not `live`).
- Hook points: `douyin/live.py`, `bilibili/live.py` `_maybe_transcribe_completed` successor `_maybe_summarize_completed`.
- `pipeline/runner.py`: optional 4th step when `summarize.enabled` (manual `pipeline run` only in v1; not required for daemon).

### 9.2 Cloud upload

When `aliyundrive.upload_transcripts: true`, also upload:

- `{basename}.summary.md`
- `{date}_merged.summary.md` if present

File kind: `summary` in `cloud_uploads` (extend enum if needed).

### 9.3 Notifications

Optional events (config-gated, default off):

- `summarize_completed`
- `summarize_merge_completed`

### 9.4 Archive index (phase 2)

Index summary body into FTS via `index_transcript_safe` sibling or new `index_summary_safe`.

---

## 10. Compliance

Every `.summary.md` begins with fixed block:

```markdown
> 个人研究档案整理，不构成投资咨询或买卖建议。请独立判断，注意风险。
```

`live_market_recap` system prompt must instruct: summarize **only what was said**; do not add buy/sell recommendations.

No new compliance gate command for v1 (unlike `archive search`); disclaimer in output is sufficient.

---

## 11. Error Handling

| Case | Behavior |
|------|----------|
| Missing transcript | Skip with error entry; exit 4 if batch |
| OpenAI rate limit / timeout | Retry once; then error per file |
| Empty transcript | Skip, log `empty_transcript` |
| Merge with mismatched creators | Fail fast exit 1 |
| Merge without all transcripts | Fail with list of missing |

Summarize errors never revert transcribe or upload state.

---

## 12. Testing

| Test | Scope |
|------|-------|
| `test_summarize_chunker.py` | Segment boundaries, char budget |
| `test_summarize_grouper.py` | Same-day pairs, gap threshold, no false merge |
| `test_summarize_writer.py` | Sidecar paths, disclaimer header |
| `test_summarize_merge.py` | Mock LLM merge of two fixture transcripts |
| `test_summarize_cli.py` | `--json` shape including `suggested_groups` |
| `test_manifest_summary_paths.py` | `summary_path` + `live_groups` |

Fixtures: shortened `transcript.json` from real segment structure (no API keys in CI).

---

## 13. Documentation Updates (post-impl)

- `README.md` — summarize section + merge workflow
- `CLAUDE.md` — commands, sidecar paths, suggested_groups flow
- `config.example.yaml` — `summarize` block

---

## 14. Implementation Phases

| Phase | Deliverable |
|-------|-------------|
| **P1** | `core/summarize/*`, `summarize run`, config, per-file sidecars, tests |
| **P2** | `grouper` + `suggested_groups` in JSON |
| **P3** | `summarize merge` + manifest `live_groups` |
| **P4** | `on_transcribe_complete` hook + cloud sidecar upload |
| **P5** | notify events, archive FTS (optional) |

---

## 15. Decisions Log

| Date | Decision |
|------|----------|
| 2026-06-01 | Profiles: **C** — live + vod + neutral; `default_profile: auto` |
| 2026-06-01 | Split live merge: **B** — `suggested_groups` only; explicit `summarize merge` |
| 2026-06-01 | LLM: **NVIDIA integrate API** + `deepseek-ai/deepseek-v4-pro`; env `NVIDIA_API_KEY`; `thinking: false` |
| 2026-06-01 | Summarize decoupled from `transcribe.engine` (transcribe stays Deepgram/whisper/etc.) |

## 16. Open Questions (v2 — shipped)

- Cross-midnight sessions — `summarize.merge.merge_cross_midnight` (default `false`)
- Per-part summary skip — `summarize.merge.per_part` (default `true`; `false` skips part `.summary.md` in multi-session groups)
- Local Ollama — add OpenAI-compatible provider under `summarize.llm.providers` (`engine` stays `openai`)
- Structured sections — `summarize.parse_sections` (default `true`); `##` headings → `sections[]` in `.summary.json`
