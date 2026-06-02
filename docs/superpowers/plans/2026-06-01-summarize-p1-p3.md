# Summarize (P1–P3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `media2text summarize run` and `summarize merge` with NVIDIA Chat API, per-file `.summary.md`, `suggested_groups` for split live sessions, and merged `{YYYYMMDD}_merged.summary.md` plus manifest `summary_path` / `live_groups`.

**Architecture:** New `core/summarize/` package mirrors `core/transcribe/`: read `.transcript.json` → chunk → map-reduce LLM (`OpenAISummarizeBackend`) → write sidecars; `grouper` reads `live_sessions` heuristics; `merger` stitches multi-part transcripts. CLI follows `cli/transcribe.py` + `emit()` JSON. Config uses `summarize.llm` (not `transcribe.openai`) to avoid model/key confusion.

**Tech Stack:** Python 3.12+, Typer, Pydantic settings, OpenAI SDK (`".[transcribe-cloud]"`), pytest, existing SQLite `live_sessions`.

**Scope:** P1 + P2 + P3 per user choice **C**. **Out of scope for this plan:** P4 (`on_transcribe_complete` hooks), P5 (notify, archive FTS), standalone `summarize suggest` command, cloud upload of summaries.

**Spec:** [docs/superpowers/specs/2026-06-01-summarize-design.md](../specs/2026-06-01-summarize-design.md)

---

## File map

| File | Responsibility |
|------|----------------|
| `src/media2text/core/summarize/__init__.py` | Public exports |
| `src/media2text/core/summarize/base.py` | `SummaryResult`, profile constants, disclaimer |
| `src/media2text/core/summarize/errors.py` | `SummarizeConfigError`, `SummarizeError` |
| `src/media2text/core/summarize/reader.py` | Load transcript JSON / `content.md` |
| `src/media2text/core/summarize/chunker.py` | Segment-aware chunks |
| `src/media2text/core/summarize/prompts.py` | System/user templates per profile |
| `src/media2text/core/summarize/openai_backend.py` | Chat Completions + map-reduce |
| `src/media2text/core/summarize/writer.py` | `.summary.md` / metadata `.summary.json` |
| `src/media2text/core/summarize/grouper.py` | `suggested_groups` |
| `src/media2text/core/summarize/merger.py` | Multi-session merge pipeline |
| `src/media2text/core/summarize/factory.py` | `create_summarize_backend`, availability check |
| `src/media2text/core/summarize/runner.py` | Batch `run` / `merge` orchestration (keeps CLI thin) |
| `src/media2text/cli/summarize.py` | Typer commands |
| `src/media2text/core/config.py` | `SummarizeConfig` tree |
| `src/media2text/core/manifest.py` | `summary_path`, `live_groups` |
| `src/media2text/core/storage/repos.py` | `LiveSessionRepo.list_completed_for_creator` |
| `src/media2text/cli/main.py` | Register `summarize` typer |
| `config.example.yaml` | `summarize:` block |
| `.env.example` | Already has `NVIDIA_API_KEY` comment |
| `tests/fixtures/summarize/` | Short transcript JSON fixtures |
| `tests/unit/test_summarize_*.py` | Unit tests (6 files) |

---

### Task 0: Spec alignment (doc-only)

**Files:**
- Modify: `docs/superpowers/specs/2026-06-01-summarize-design.md`

- [ ] **Step 1: Fix config key naming in spec**

Replace `summarize.openai:` with `summarize.llm:` in §5 and §3.2 layout comment.

- [ ] **Step 2: Fix hook config typo**

§9.1: `live.summarize_on_complete` → `summarize.on_transcribe_complete`.

- [ ] **Step 3: Clarify P1 JSON scope**

§4.3: note v1 `.summary.json` is **metadata only** (no parsed `sections`); structured sections = v2.

- [ ] **Step 4: Merge disambiguation**

§7.2: when multiple `suggested_groups` on same date, require `--sessions` or `--group-index N` (no bare `--creator --date`).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-01-summarize-design.md
git commit -m "docs: align summarize spec with eng review (llm key, merge flags)"
```

---

### Task 1: Config models

**Files:**
- Modify: `src/media2text/core/config.py`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing test**

```python
def test_summarize_config_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.summarize.enabled is False
    assert cfg.summarize.llm.api_key_env == "NVIDIA_API_KEY"
    assert cfg.summarize.llm.model == "deepseek-ai/deepseek-v4-pro"
    assert cfg.summarize.merge_gap_minutes == 60
```

- [ ] **Step 2: Run test**

Run: `pytest tests/unit/test_config.py::test_summarize_config_defaults -v`  
Expected: FAIL (`AppConfig` has no `summarize`)

- [ ] **Step 3: Add Pydantic models**

In `config.py`, after `TranscribeConfig`:

```python
class SummarizeLlmConfig(BaseModel):
    api_key_env: str = "NVIDIA_API_KEY"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "deepseek-ai/deepseek-v4-pro"
    temperature: float = 0.2
    top_p: float = 0.95
    max_output_tokens: int = 4096
    thinking: bool = False


class SummarizeChunkConfig(BaseModel):
    max_chars: int = 24000
    minutes: float = 30.0


class SummarizeMergeConfig(BaseModel):
    auto_merge_after_parts: bool = False


class SummarizeConfig(BaseModel):
    enabled: bool = False
    engine: str = "openai"
    on_transcribe_complete: bool = False
    default_profile: str = "auto"
    merge_gap_minutes: int = 60
    merge_date_tz: str = "UTC"
    max_files_per_run: int = 0
    llm: SummarizeLlmConfig = Field(default_factory=SummarizeLlmConfig)
    chunk: SummarizeChunkConfig = Field(default_factory=SummarizeChunkConfig)
    merge: SummarizeMergeConfig = Field(default_factory=SummarizeMergeConfig)
```

Add to `AppConfig`:

```python
summarize: SummarizeConfig = Field(default_factory=SummarizeConfig)
```

- [ ] **Step 4: Append `config.example.yaml` block**

```yaml
summarize:
  enabled: false
  engine: openai
  on_transcribe_complete: false
  default_profile: auto
  merge_gap_minutes: 60
  merge_date_tz: UTC
  max_files_per_run: 0
  llm:
    api_key_env: NVIDIA_API_KEY
    base_url: https://integrate.api.nvidia.com/v1
    model: deepseek-ai/deepseek-v4-pro
    temperature: 0.2
    top_p: 0.95
    max_output_tokens: 4096
    thinking: false
  chunk:
    max_chars: 24000
    minutes: 30
  merge:
    auto_merge_after_parts: false
```

- [ ] **Step 5: Run test**

Run: `pytest tests/unit/test_config.py::test_summarize_config_defaults -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/media2text/core/config.py config.example.yaml tests/unit/test_config.py
git commit -m "feat: add summarize config models"
```

---

### Task 2: Summarize base + errors

**Files:**
- Create: `src/media2text/core/summarize/__init__.py`
- Create: `src/media2text/core/summarize/base.py`
- Create: `src/media2text/core/summarize/errors.py`

- [ ] **Step 1: Implement base**

`base.py`:

```python
from dataclasses import dataclass

DISCLAIMER_MD = (
    "> 个人研究档案整理，不构成投资咨询或买卖建议。请独立判断，注意风险。\n"
)

PROFILES = frozenset({
    "auto",
    "live_market_recap",
    "vod_highlights",
    "neutral_minutes",
})


@dataclass
class SummaryResult:
    engine: str
    model: str
    profile: str
    markdown: str
    chunks: int
    provider_base_url: str | None = None
```

`errors.py`: `SummarizeConfigError`, `SummarizeError` (subclass `Exception`, mirror transcribe).

- [ ] **Step 2: Commit**

```bash
git add src/media2text/core/summarize/
git commit -m "feat: summarize base types and errors"
```

---

### Task 3: Transcript reader

**Files:**
- Create: `src/media2text/core/summarize/reader.py`
- Create: `tests/fixtures/summarize/short_live.json`
- Test: `tests/unit/test_summarize_reader.py`

Fixture `short_live.json`:

```json
{
  "engine": "deepgram",
  "text": "测试直播片段",
  "segments": [
    {"start": 0.0, "end": 5.0, "text": "大家好"},
    {"start": 5.0, "end": 12.0, "text": "今天聊 AI 应用"}
  ]
}
```

- [ ] **Step 1: Write failing tests**

```python
def test_load_transcript_json(tmp_path) -> None:
    p = tmp_path / "a.transcript.json"
    p.write_text((FIXTURES / "short_live.json").read_text(), encoding="utf-8")
    doc = load_transcript(p)
    assert len(doc.segments) == 2
    assert doc.segments[0].text == "大家好"

def test_load_transcript_missing_raises(tmp_path) -> None:
    with pytest.raises(SummarizeError, match="not found"):
        load_transcript(tmp_path / "missing.transcript.json")

def test_load_content_md(tmp_path) -> None:
    md = tmp_path / "content.md"
    md.write_text("# 动态\n\n正文", encoding="utf-8")
    doc = load_content_md(md)
    assert "正文" in doc.plain_text
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_summarize_reader.py -v`

- [ ] **Step 3: Implement reader**

```python
@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

@dataclass
class TranscriptDoc:
    source_path: Path
    segments: list[TranscriptSegment]
    plain_text: str
    kind: str  # "segments" | "markdown"

def transcript_path_for_media(media: Path) -> Path:
    if media.suffix == ".transcript.json":
        return media
    return media.with_suffix(".transcript.json")

def load_transcript(path: Path) -> TranscriptDoc: ...
def load_content_md(path: Path) -> TranscriptDoc: ...
```

Empty segments → raise `SummarizeError("empty_transcript")`.

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/summarize/reader.py tests/
git commit -m "feat: summarize transcript reader"
```

---

### Task 4: Chunker

**Files:**
- Create: `src/media2text/core/summarize/chunker.py`
- Test: `tests/unit/test_summarize_chunker.py`

- [ ] **Step 1: Write failing tests**

```python
def test_single_chunk_short_text():
    segs = [TranscriptSegment(0, 10, "a" * 100)]
    chunks = chunk_segments(segs, max_chars=24000, max_minutes=30)
    assert len(chunks) == 1

def test_splits_when_char_budget_exceeded():
    segs = [
        TranscriptSegment(0, 60, "x" * 15000),
        TranscriptSegment(60, 120, "y" * 15000),
    ]
    chunks = chunk_segments(segs, max_chars=20000, max_minutes=999)
    assert len(chunks) == 2
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`chunk_segments` returns `list[list[TranscriptSegment]]`, greedy pack by char count of formatted lines `"[{start}-{end}] {text}"`, break when exceeds `max_chars` or span > `max_minutes * 60`.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/summarize/chunker.py tests/unit/test_summarize_chunker.py
git commit -m "feat: summarize segment chunker"
```

---

### Task 5: Prompts + profile resolution

**Files:**
- Create: `src/media2text/core/summarize/prompts.py`
- Test: `tests/unit/test_summarize_prompts.py`

- [ ] **Step 1: Tests**

```python
def test_resolve_profile_auto_live():
    assert resolve_profile("auto", media_kind="live") == "live_market_recap"

def test_resolve_profile_auto_vod():
    assert resolve_profile("auto", media_kind="vod") == "vod_highlights"

def test_build_messages_live_contains_disclaimer_instruction():
    msgs = build_messages("live_market_recap", "chunk text")
    assert "不构成投资" in msgs[0]["content"] or "买卖" in msgs[0]["content"]
```

- [ ] **Step 2: Implement**

- `resolve_profile(name, *, media_kind: str)` — `media_kind` in `live|vod|dynamic`
- `build_messages(profile, chunk_text, *, merge_pass: bool = False)` → OpenAI message list
- `merge_pass` adds dedupe instruction for merger final call

- [ ] **Step 3: Run tests — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/summarize/prompts.py tests/unit/test_summarize_prompts.py
git commit -m "feat: summarize prompt profiles"
```

---

### Task 6: Writer

**Files:**
- Create: `src/media2text/core/summarize/writer.py`
- Test: `tests/unit/test_summarize_writer.py`

- [ ] **Step 1: Tests**

```python
def test_write_summary_sidecars(tmp_path):
    media = tmp_path / "20260601T130643Z.mp4"
    media.touch()
    result = SummaryResult(
        engine="openai",
        model="deepseek-ai/deepseek-v4-pro",
        profile="live_market_recap",
        markdown="## 核心观点\n- foo",
        chunks=2,
        provider_base_url="https://integrate.api.nvidia.com/v1",
    )
    md_path, json_path = write_summary(media, result, source_transcript=media.with_suffix(".transcript.json"))
    text = md_path.read_text(encoding="utf-8")
    assert text.startswith(DISCLAIMER_MD.strip()[:10]) or DISCLAIMER_MD.split("\n")[0] in text
    meta = json.loads(json_path.read_text())
    assert meta["profile"] == "live_market_recap"
    assert "sections" not in meta or meta.get("sections") is None
```

- [ ] **Step 2: Implement**

```python
def summary_paths_for_media(media: Path) -> tuple[Path, Path]:
    base = media.with_suffix("") if media.suffix == ".transcript.json" else media
    return base.with_suffix(".summary.md"), base.with_suffix(".summary.json")

def write_summary(media: Path, result: SummaryResult, *, source_transcript: Path) -> tuple[Path, Path]:
    md_path, json_path = summary_paths_for_media(media)
    body = DISCLAIMER_MD + "\n" + result.markdown.strip() + "\n"
    md_path.write_text(body, encoding="utf-8")
    json_path.write_text(json.dumps({...metadata only...}, ensure_ascii=False, indent=2), ...)
    return md_path, json_path

def merged_summary_paths(live_dir: Path, yyyymmdd: str) -> tuple[Path, Path]:
    stem = live_dir / f"{yyyymmdd}_merged"
    return stem.with_suffix(".summary.md"), stem.with_suffix(".summary.json")
```

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/summarize/writer.py tests/unit/test_summarize_writer.py
git commit -m "feat: summarize sidecar writer"
```

---

### Task 7: OpenAI backend (mockable)

**Files:**
- Create: `src/media2text/core/summarize/openai_backend.py`
- Create: `src/media2text/core/summarize/factory.py`
- Test: `tests/unit/test_summarize_openai_backend.py`

- [ ] **Step 1: Protocol for tests**

```python
class SummarizeBackend(Protocol):
    def summarize_text(self, profile: str, text: str) -> str: ...
```

- [ ] **Step 2: Test with fake backend injected in runner later; unit test backend formatting**

```python
def test_extra_body_thinking_false():
    cfg = SummarizeLlmConfig(thinking=False, model="deepseek-ai/deepseek-v4-pro")
    assert build_chat_kwargs(cfg).get("extra_body") == {"chat_template_kwargs": {"thinking": False}}

def test_extra_body_omitted_when_thinking_true():
    cfg = SummarizeLlmConfig(thinking=True, model="gpt-4o")
    assert "extra_body" not in build_chat_kwargs(cfg)
```

- [ ] **Step 3: Implement OpenAISummarizeBackend**

- `_client()` same pattern as `cloud_openai.py` but Chat Completions
- `summarize_chunks(profile, chunks: list[str]) -> str`: map partial summaries, then reduce
- On any chunk failure after 1 retry: raise `SummarizeError` (no partial file write — caller responsibility)
- `create_summarize_backend(cfg) -> OpenAISummarizeBackend`
- `summarize_engine_available(cfg) -> tuple[bool, str | None]` checks `enabled`, API key env, openai import

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/summarize/openai_backend.py src/media2text/core/summarize/factory.py tests/unit/test_summarize_openai_backend.py
git commit -m "feat: OpenAI-compatible summarize backend"
```

---

### Task 8: Grouper + repo helper

**Files:**
- Create: `src/media2text/core/summarize/grouper.py`
- Modify: `src/media2text/core/storage/repos.py`
- Test: `tests/unit/test_summarize_grouper.py`

- [ ] **Step 1: Add repo method**

```python
def list_completed_for_creator(self, creator_id: str) -> list[LiveSessionRow]:
    rows = self._conn.execute(
        """
        SELECT * FROM live_sessions
        WHERE creator_id = ? AND status = 'completed' AND local_path IS NOT NULL
        ORDER BY started_at ASC
        """,
        (creator_id,),
    ).fetchall()
    return [LiveSessionRow(**dict(r)) for r in rows]
```

- [ ] **Step 2: Tests (31min gap case)**

Use three synthetic sessions same calendar day UTC:

```python
def test_suggested_group_two_parts_31min_gap():
    # A ended 12:00, B started 12:31 -> one group, gap_minutes=31
    groups = build_suggested_groups(rows, merge_gap_minutes=60, workspace=ws)
    assert len(groups) == 1
    assert len(groups[0].session_ids) == 2

def test_no_group_when_gap_90min():
    ...
```

Implement `session_end_ts(row)` → `ended_at` or fallback `started_at`.

Implement `build_suggested_groups(*, creator_id, rows, workspace, merge_gap_minutes, tz)` returning dataclass list with `date`, `session_ids`, `media_paths`, `gap_minutes`, `room_id`, `group_index`, `merge_command` string.

Chain rule: A-B gap ok and B-C gap ok → **one** group `[A,B,C]` (spec §8.2).

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/summarize/grouper.py src/media2text/core/storage/repos.py tests/unit/test_summarize_grouper.py
git commit -m "feat: live session suggested_groups grouper"
```

---

### Task 9: Merger

**Files:**
- Create: `src/media2text/core/summarize/merger.py`
- Create: `tests/fixtures/summarize/part1.json`, `part2.json`
- Test: `tests/unit/test_summarize_merge.py`

- [ ] **Step 1: Tests with stub backend**

```python
class StubBackend:
    def summarize_text(self, profile: str, text: str) -> str:
        return f"SUMMARY:{profile}:{len(text)}"

def test_merge_two_parts_writes_merged_sidecar(tmp_path, monkeypatch):
    ...
    md, _ = merge_sessions(cfg, backend=StubBackend(), sessions=[...], workspace=ws)
    assert md.name == "20260601_merged.summary.md"
```

- [ ] **Step 2: Implement merger**

- Validate same `creator_id`
- Load each transcript; tag segments with `part_index` in prompt text
- Reuse chunker + backend map-reduce
- `write_merged_summary(live_dir, date_yyyymmdd, result, sources: list[dict])`
- JSON includes `"merged": true`, `"sources": [...]`

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/summarize/merger.py tests/
git commit -m "feat: summarize merge pipeline"
```

---

### Task 10: Runner orchestration

**Files:**
- Create: `src/media2text/core/summarize/runner.py`
- Test: `tests/unit/test_summarize_runner.py` (light)

- [ ] **Step 1: Implement `summarize_one(media, cfg, backend, *, profile, force)`**

Skip if `.summary.md` exists and not `force`. Detect `media_kind` from path (`/live/` → live, `/videos/` → vod, `content.md` → dynamic).

- [ ] **Step 2: Implement `run_batch(cfg, *, paths, creator_id, profile, force, limit)`**

Returns dict matching CLI JSON: `summarized`, `skipped`, `results`, `errors`, `suggested_groups` (if `creator_id`).

Discover targets:

- explicit paths (file/dir glob `**/*.transcript.json` and `**/*.mp4` with transcript)
- `--creator`: awemes with transcript + live_sessions completed with transcript sidecar, skip if summary exists

Apply `max_files_per_run` / `limit`.

- [ ] **Step 3: Implement `merge_batch(cfg, *, session_ids, paths, creator_id, date, group_index, profile, force)`**

Resolve sessions from DB; error if `--creator --date` matches 0 or 2+ groups without `group_index`.

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/summarize/runner.py
git commit -m "feat: summarize run/merge orchestration"
```

---

### Task 11: Manifest `summary_path` + `live_groups`

**Files:**
- Modify: `src/media2text/core/manifest.py`
- Test: `tests/unit/test_manifest_summary_paths.py`

- [ ] **Step 1: Failing test**

```python
def test_manifest_includes_summary_path_and_live_groups(tmp_path, monkeypatch):
    ...
    merged = live_dir / "20260601_merged.summary.md"
    merged.write_text("merged", encoding="utf-8")
    out = refresh_manifest(conn, sec_uid=sec_uid, workspace=ws)
    payload = json.loads(out.read_text())
    live_item = payload["live"][0]
    assert live_item["summary_path"] == str(per_file_summary)
    assert payload["live_groups"][0]["summary_path"] == str(merged)
```

- [ ] **Step 2: Implement**

```python
def _summary_sidecar_path(media_path: str | None) -> str | None:
    if not media_path:
        return None
    p = Path(media_path).with_suffix(".summary.md")
    return str(p) if p.is_file() else None

def _discover_live_groups(live_dir: Path) -> list[dict]:
    groups = []
    for md in sorted(live_dir.glob("*_merged.summary.md")):
        # parse date from filename YYYYMMDD_merged
        groups.append({"date": iso_date, "summary_path": str(md), "session_ids": []})
    return groups
```

Add `summary_path` to live + vod entries in `refresh_manifest`. Add top-level `live_groups` (scan `live/*_merged.summary.md`; optionally enrich `session_ids` from merged JSON `sources` if present).

Persist `session_ids` into merged `.summary.json` in merger so manifest can list them.

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/manifest.py tests/unit/test_manifest_summary_paths.py
git commit -m "feat: manifest summary_path and live_groups"
```

---

### Task 12: CLI

**Files:**
- Create: `src/media2text/cli/summarize.py`
- Modify: `src/media2text/cli/main.py`
- Test: `tests/unit/test_summarize_cli.py`

- [ ] **Step 1: CLI tests (Typer `CliRunner`)**

```python
def test_summarize_run_json_shape(monkeypatch, tmp_path):
    monkeypatch.setattr("media2text.cli.summarize.run_batch", lambda *a, **k: {...})
    result = runner.invoke(app, ["summarize", "run", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "suggested_groups" in data
```

- [ ] **Step 2: Implement commands**

```python
app = typer.Typer(help="LLM transcript summarize")

@app.command("run")
def run_cmd(path: Path | None = None, creator: str | None = Option(None, "--creator"), ...):

@app.command("merge")
def merge_cmd(
    sessions: str | None = Option(None, "--sessions"),
    paths: str | None = Option(None, "--paths"),
    creator: str | None = Option(None, "--creator"),
    date: str | None = Option(None, "--date"),
    group_index: int | None = Option(None, "--group-index"),
    ...
):
```

Exit codes: 0 / 1 (config) / 4 (partial errors). Check `cfg.summarize.enabled` — if false, exit 1 with message unless `MEDIA2TEXT_SUMMARIZE=1` override not needed (keep simple: require `enabled: true`).

Register in `main.py`:

```python
from media2text.cli import summarize as summarize_cli
app.add_typer(summarize_cli.app, name="summarize")
```

- [ ] **Step 3: Run tests — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/media2text/cli/summarize.py src/media2text/cli/main.py tests/unit/test_summarize_cli.py
git commit -m "feat: summarize CLI run and merge"
```

---

### Task 13: Doctor check (optional small)

**Files:**
- Modify: `src/media2text/cli/doctor.py` (if exists summarize section)

- [ ] **Step 1: When `summarize.enabled`, report NVIDIA_API_KEY / openai SDK / base_url reachability skip (no live ping required)**

- [ ] **Step 2: Commit**

```bash
git add src/media2text/cli/doctor.py
git commit -m "feat: doctor checks summarize LLM config"
```

---

### Task 14: Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add command table entries** for `summarize run`, `summarize merge`, JSON `suggested_groups`, sidecar paths, env `NVIDIA_API_KEY`, config `summarize.enabled`.

- [ ] **Step 2: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: summarize CLI and sidecar conventions"
```

---

### Task 15: Full test suite

- [ ] **Step 1: Run**

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/unit/test_summarize_*.py tests/unit/test_manifest_summary_paths.py -v
pytest tests/ -v
```

Expected: all pass, no live NVIDIA calls in CI.

- [ ] **Step 2: Manual smoke (local)**

```bash
# config.yaml: summarize.enabled: true
media2text summarize run data/creators/<sec_uid>/live/20260601T130643Z.mp4 --json
media2text summarize run --creator <id> --json   # expect suggested_groups
media2text summarize merge --sessions <id1>,<id2> --json
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| G1 CLI run/merge `--json` | Task 12 |
| G2 input `.transcript.json` | Task 3 |
| G3 map-reduce chunking | Task 4, 7 |
| G4 profile auto | Task 5, 10 |
| G5 suggested_groups | Task 8, 10, 12 |
| G6 explicit merge | Task 9, 12 |
| G7 disclaimer | Task 2, 6 |
| G8 manifest summary_path | Task 11 |
| Merged naming `YYYYMMDD_merged` | Task 6, 9 |
| Exit codes 0/1/4 | Task 12 |
| Unit tests mock LLM | Tasks 3–12 |
| NVIDIA + thinking:false | Task 1, 7 |
| Decision B no auto merge | Task 1 `auto_merge_after_parts: false` |
| §12 test file list | All `test_summarize_*` |
| P4 hooks / cloud | **Not in plan** (follow-up PR) |
| `summarize suggest` command | **Dropped** (use `run --json`) |
| JSON `sections` parse | **Deferred** v2; metadata only Task 6 |

**Placeholder scan:** None.

**Type consistency:** `SummarizeLlmConfig` used throughout; not `OpenAIConfig` from transcribe.

---

## Parallelization

| Lane | Tasks | Notes |
|------|-------|-------|
| A | 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 | Core library |
| B | 8 | After Task 3+6 |
| C | 9 | After 3–7 |
| D | 10 → 11 → 12 | Integration |
| E | 13 → 14 → 15 | Polish |

Run **sequentially** A then B,C parallel only if two worktrees; manifest (11) must follow merger (9).

---

## NOT in scope (this plan)

- `summarize.on_transcribe_complete` live hooks (P4)
- Aliyun upload of `.summary.md` (P4)
- Notify events (P5)
- Archive FTS on summaries (P5)
- Cross-midnight merge
- Ollama / multi-vendor backends

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-06-01-summarize-p1-p3.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — implement in this session with executing-plans checkpoints  

Which approach do you want?
