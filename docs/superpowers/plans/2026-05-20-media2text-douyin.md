# media2text Douyin CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a personal CLI that logs into Douyin, watches followed creators for live streams, records video (flv/ts → remux mp4), then syncs VOD and transcribes to JSON/Markdown for Agent use.

**Architecture:** Thin Typer CLI over `DouyinAdapterV1` (httpx + cookies, Playwright fallback), SQLite WAL workspace DB, ffmpeg subprocesses for live capture, pluggable transcribe backends. Live-first: P0–P1 gate on `doctor` + `live watch`; P2–P4 add VOD + pipeline.

**Tech Stack:** Python 3.12+, Typer, Pydantic v2, httpx, Playwright, SQLite3, faster-whisper (optional dep), structlog, pytest, ruff, pyright

**Spec:** `docs/superpowers/specs/2026-05-20-media2text-douyin-design.md`

---

## Prerequisites (human / one-time)

```bash
# macOS example
brew install ffmpeg
cd /Users/Oychao/Documents/Projects/media2text
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv not installed
uv venv && source .venv/bin/activate
playwright install chromium
```

---

## Target file map

```
pyproject.toml
config.example.yaml
.gitignore
README.md
src/media2text/
  __init__.py
  __main__.py
  cli/
    __init__.py
    main.py
    auth.py
    creator.py
    live.py
    download.py
    transcribe.py
    pipeline.py
    doctor.py
  core/
    config.py
    errors.py
    exit_codes.py
    logging.py
    json_out.py
    workspace.py
    platform/
      base.py
      douyin/
        __init__.py
        adapter.py
        auth.py
        resolver.py
        catalog.py
        download.py
        live.py
        fixtures/
          is_live_true.json
          is_live_false.json
    storage/
      db.py
      models.py
      repos.py
    transcribe/
      base.py
      whisper.py
      cloud_openai.py
    pipeline/
      runner.py
    manifest.py
    ffmpeg.py
    process_lock.py
  schemas/
    responses.py
tests/
  conftest.py
  unit/
    test_config.py
    test_storage.py
    test_process_lock.py
    test_ffmpeg_remux.py
    test_douyin_adapter.py
    test_live_watcher.py
  integration/
    test_cli_doctor.py
    test_cli_auth.py
```

---

## Phase P0 — Scaffold, config, storage, auth, doctor

### Task 1: Project scaffold and packaging

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/media2text/__init__.py`, `src/media2text/__main__.py`, `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "media2text"
version = "0.1.0"
description = "Douyin live/VOD capture and transcribe CLI for agents"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "httpx>=0.27",
  "playwright>=1.42",
  "structlog>=24.1",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
transcribe = ["faster-whisper>=1.0"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.3", "pyright>=1.1"]

[project.scripts]
media2text = "media2text.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/media2text"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: needs real Douyin network"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pyright]
include = ["src"]
```

- [ ] **Step 2: Create package entrypoints**

`src/media2text/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/media2text/__main__.py`:
```python
from media2text.cli.main import app

app()
```

- [ ] **Step 3: `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
data/
*.egg-info/
dist/
.DS_Store
```

- [ ] **Step 4: Install editable**

```bash
cd /Users/Oychao/Documents/Projects/media2text
uv pip install -e ".[dev]"
media2text version
```
Expected: prints `0.1.0` or Typer help if `version` not wired yet (wire in Task 5).

- [ ] **Step 5: Commit**

```bash
git init  # if not already
git add pyproject.toml .gitignore src/media2text/__init__.py src/media2text/__main__.py README.md
git commit -m "chore: project scaffold for media2text CLI"
```

---

### Task 2: Config, workspace, errors, JSON output

**Files:**
- Create: `config.example.yaml`, `src/media2text/core/config.py`, `src/media2text/core/workspace.py`, `src/media2text/core/errors.py`, `src/media2text/core/exit_codes.py`, `src/media2text/core/json_out.py`, `src/media2text/schemas/responses.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing config test**

`tests/unit/test_config.py`:
```python
from pathlib import Path

from media2text.core.config import AppConfig


def test_load_config_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.workspace == Path("./data")
    assert cfg.platforms.douyin.poll_interval_sec == 60
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/unit/test_config.py -v
```

- [ ] **Step 3: Implement config + workspace**

`src/media2text/core/config.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DouyinPlatformConfig(BaseModel):
    poll_interval_sec: int = 60
    download_concurrency: int = 3
    max_sync_pages: int = 0


class PlatformsConfig(BaseModel):
    douyin: DouyinPlatformConfig = Field(default_factory=DouyinPlatformConfig)


class LiveConfig(BaseModel):
    transcribe_on_complete: bool = False
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_stop_timeout_sec: int = 30
    temp_format: str = "flv"


class WhisperConfig(BaseModel):
    model: str = "medium"
    device: str = "auto"


class TranscribeConfig(BaseModel):
    engine: str = "whisper"
    language: str = "zh"
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)


class AppConfig(BaseSettings):
    workspace: Path = Path("./data")
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)

    @classmethod
    def load(cls) -> AppConfig:
        path = os.environ.get("MEDIA2TEXT_CONFIG", "config.yaml")
        if Path(path).is_file():
            data = yaml.safe_load(Path(path).read_text()) or {}
            return cls.model_validate(data)
        return cls()

    def ensure_workspace(self) -> Path:
        root = self.workspace.resolve()
        for sub in ("sessions", "creators"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root
```

`src/media2text/core/errors.py`:
```python
class Media2TextError(Exception):
    code: str = "error"


class AuthRequired(Media2TextError):
    code = "auth_required"


class RateLimited(Media2TextError):
    code = "rate_limited"


class ParseFailed(Media2TextError):
    code = "parse_failed"


class PlatformChanged(Media2TextError):
    code = "platform_changed"


class RecordingError(Media2TextError):
    code = "recording_error"
```

`src/media2text/core/exit_codes.py`:
```python
EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_AUTH = 2
EXIT_PARSE = 3
EXIT_PARTIAL = 4


def exit_code_for(exc: Exception) -> int:
    from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged

    if isinstance(exc, AuthRequired):
        return EXIT_AUTH
    if isinstance(exc, (ParseFailed, PlatformChanged)):
        return EXIT_PARSE
    return EXIT_GENERAL
```

`src/media2text/core/json_out.py`:
```python
import json
import sys
from typing import Any


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(payload.get("message", json.dumps(payload, ensure_ascii=False)) + "\n")
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/unit/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/ tests/unit/test_config.py config.example.yaml
git commit -m "feat: add config, workspace, errors, and JSON output helpers"
```

---

### Task 3: SQLite storage (WAL) + repositories

**Files:**
- Create: `src/media2text/core/storage/db.py`, `models.py`, `repos.py`
- Test: `tests/unit/test_storage.py`

- [ ] **Step 1: Write failing storage test**

`tests/unit/test_storage.py`:
```python
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo


def test_creator_roundtrip(tmp_path):
    conn = connect(tmp_path / "media2text.db")
    repo = CreatorRepo(conn)
    cid = repo.add(sec_uid="sec123", profile_url="https://www.douyin.com/user/x", watch_live=True)
    row = repo.get(cid)
    assert row is not None
    assert row.sec_uid == "sec123"
    assert row.watch_live == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/test_storage.py -v
```

- [ ] **Step 3: Implement storage**

`src/media2text/core/storage/db.py`:
```python
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS creators (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  sec_uid TEXT NOT NULL UNIQUE,
  display_name TEXT,
  profile_url TEXT,
  watch_live INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS awemes (
  aweme_id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  title TEXT,
  create_time INTEGER,
  media_type TEXT,
  sync_status TEXT NOT NULL,
  local_path TEXT,
  transcribe_status TEXT,
  transcript_path TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  room_id TEXT,
  ffmpeg_pid INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  local_path TEXT,
  temp_path TEXT,
  status TEXT NOT NULL,
  error TEXT,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
```

`src/media2text/core/storage/models.py`:
```python
from dataclasses import dataclass


@dataclass
class CreatorRow:
    id: str
    platform: str
    sec_uid: str
    display_name: str | None
    profile_url: str | None
    watch_live: int
    created_at: str
```

`src/media2text/core/storage/repos.py`:
```python
import uuid
from datetime import datetime, timezone

from media2text.core.storage.models import CreatorRow


class CreatorRepo:
    def __init__(self, conn):
        self._conn = conn

    def add(self, *, sec_uid: str, profile_url: str, watch_live: bool) -> str:
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO creators (id, platform, sec_uid, profile_url, watch_live, created_at)
            VALUES (?, 'douyin', ?, ?, ?, ?)
            """,
            (cid, sec_uid, profile_url, 1 if watch_live else 0, now),
        )
        self._conn.commit()
        return cid

    def get(self, creator_id: str) -> CreatorRow | None:
        row = self._conn.execute("SELECT * FROM creators WHERE id = ?", (creator_id,)).fetchone()
        if not row:
            return None
        return CreatorRow(**dict(row))

    def list_all(self) -> list[CreatorRow]:
        rows = self._conn.execute("SELECT * FROM creators ORDER BY created_at").fetchall()
        return [CreatorRow(**dict(r)) for r in rows]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/unit/test_storage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/storage/ tests/unit/test_storage.py
git commit -m "feat: SQLite WAL schema and creator repository"
```

---

### Task 4: Typer app shell + structlog

**Files:**
- Create: `src/media2text/core/logging.py`, `src/media2text/cli/main.py`, `src/media2text/cli/__init__.py`
- Test: `tests/integration/test_cli_doctor.py` (skeleton)

- [ ] **Step 1: structlog stderr JSON**

`src/media2text/core/logging.py`:
```python
import logging
import structlog


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

- [ ] **Step 2: Typer root app**

`src/media2text/cli/main.py`:
```python
import typer

from media2text import __version__
from media2text.core.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="Douyin media capture and transcribe CLI")


@app.callback()
def main() -> None:
    configure_logging()


@app.command()
def version() -> None:
    typer.echo(__version__)


# Subcommands registered in later tasks:
# from media2text.cli import auth, doctor, creator, live
```

- [ ] **Step 3: Verify CLI**

```bash
media2text version
```
Expected: `0.1.0`

- [ ] **Step 4: Commit**

```bash
git add src/media2text/cli/ src/media2text/core/logging.py
git commit -m "feat: Typer app shell and structured logging"
```

---

### Task 5: Douyin auth (Playwright) + `auth login/status`

**Files:**
- Create: `src/media2text/core/platform/douyin/auth.py`, `src/media2text/cli/auth.py`
- Test: manual + `tests/integration/test_cli_auth.py` (mock playwright optional)

- [ ] **Step 1: Session path helper**

`src/media2text/core/platform/douyin/auth.py`:
```python
from pathlib import Path

from playwright.sync_api import sync_playwright


SESSION_NAME = "douyin.json"


def session_path(workspace: Path) -> Path:
    return workspace / "sessions" / SESSION_NAME


def login_interactive(workspace: Path, *, headless: bool = False) -> Path:
    path = session_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
        # User completes QR/login in browser window
        input("Press Enter after you have logged in to Douyin...")
        context.storage_state(path=str(path))
        browser.close()
    path.chmod(0o600)
    return path


def session_exists(workspace: Path) -> bool:
    return session_path(workspace).is_file()
```

- [ ] **Step 2: CLI commands**

`src/media2text/cli/auth.py`:
```python
import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.platform.douyin.auth import login_interactive, session_exists

app = typer.Typer(help="Authentication")


@app.command("login")
def login(
    platform: str = typer.Option("douyin", "--platform"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    if platform != "douyin":
        raise typer.BadParameter("Only douyin supported in MVP")
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    path = login_interactive(ws, headless=False)
    emit({"ok": True, "command": "auth login", "session_path": str(path)}, as_json=json_out)


@app.command("status")
def status(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    emit(
        {
            "ok": True,
            "command": "auth status",
            "session_exists": session_exists(ws),
            "auth_required": not session_exists(ws),
        },
        as_json=json_out,
    )
```

Register in `cli/main.py`:
```python
from media2text.cli import auth as auth_cli
app.add_typer(auth_cli.app, name="auth")
```

- [ ] **Step 3: Manual test**

```bash
media2text auth login --platform douyin
media2text auth status --json
```
Expected: `session_exists: true`

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/platform/douyin/auth.py src/media2text/cli/auth.py src/media2text/cli/main.py
git commit -m "feat: Douyin Playwright login and auth status"
```

---

### Task 6: `doctor` command

**Files:**
- Create: `src/media2text/cli/doctor.py`
- Test: `tests/integration/test_cli_doctor.py`

- [ ] **Step 1: Write failing doctor test**

`tests/integration/test_cli_doctor.py`:
```python
import json
from typer.testing import CliRunner

from media2text.cli.main import app


def test_doctor_json_missing_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(c["name"] == "ffmpeg" and not c["ok"] for c in payload["checks"])
```

- [ ] **Step 2: Implement doctor**

`src/media2text/cli/doctor.py`:
```python
import shutil
import shutil as sh
from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.exit_codes import EXIT_GENERAL, EXIT_OK
from media2text.core.json_out import emit
from media2text.core.platform.douyin.auth import session_exists

app = typer.Typer(help="Environment checks")


def _disk_ok(path: Path, min_gb: float = 5.0) -> bool:
    usage = sh.disk_usage(path)
    return usage.free >= min_gb * (1024**3)


@app.command()
def doctor(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    checks = [
        {"name": "ffmpeg", "ok": bool(shutil.which(cfg.live.ffmpeg_path))},
        {"name": "playwright", "ok": bool(shutil.which("playwright"))},
        {"name": "session", "ok": session_exists(ws), "auth_required": not session_exists(ws)},
        {"name": "disk", "ok": _disk_ok(ws)},
    ]
    ok = all(c["ok"] for c in checks if c["name"] != "session") and checks[2]["ok"]
    payload = {"ok": ok, "command": "doctor", "checks": checks}
    emit(payload, as_json=json_out)
    raise typer.Exit(EXIT_OK if ok else EXIT_GENERAL)
```

Wire `app.add_typer(doctor_cli.app, name="doctor")` — or single command on root.

- [ ] **Step 3: Run test**

```bash
pytest tests/integration/test_cli_doctor.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/media2text/cli/doctor.py tests/integration/test_cli_doctor.py
git commit -m "feat: doctor command for ffmpeg, session, disk checks"
```

**P0 gate:** `media2text doctor --json` → all checks ok (with ffmpeg + session).

---

## Phase P1 — Live watch MVP (highest priority)

### Task 7: httpx client from Playwright storage_state

**Files:**
- Create: `src/media2text/core/platform/douyin/httpx_client.py`
- Modify: `adapter.py` (skeleton)

- [ ] **Step 1: Cookie loader**

`src/media2text/core/platform/douyin/httpx_client.py`:
```python
import json
from pathlib import Path

import httpx


def client_from_storage(session_file: Path, *, timeout: float = 30.0) -> httpx.Client:
    data = json.loads(session_file.read_text())
    cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
    return httpx.Client(
        cookies=cookies,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.douyin.com/",
        },
        timeout=timeout,
        follow_redirects=True,
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/media2text/core/platform/douyin/httpx_client.py
git commit -m "feat: build httpx client from Playwright session cookies"
```

---

### Task 8: DouyinAdapterV1 — `is_live` + `resolve_stream_url` (fixtures)

**Files:**
- Create: `src/media2text/core/platform/douyin/adapter.py`, fixtures, `tests/unit/test_douyin_adapter.py`

- [ ] **Step 1: Add fixture files** (replace with real captured responses when available)

`fixtures/is_live_false.json` — minimal stub:
```json
{"data": {"live_status": 0}}
```

`fixtures/is_live_true.json`:
```json
{"data": {"live_status": 1, "stream_url": "https://example.com/live.flv"}}
```

- [ ] **Step 2: Write failing adapter test**

`tests/unit/test_douyin_adapter.py`:
```python
import json
from pathlib import Path

from media2text.core.platform.douyin.adapter import DouyinAdapterV1


def test_is_live_false_from_fixture(tmp_path):
    fx = Path(__file__).parents[2] / "src/media2text/core/platform/douyin/fixtures/is_live_false.json"
    adapter = DouyinAdapterV1(client=None, fixture_root=fx.parent)
    assert adapter.is_live(sec_uid="fake", room_id="123") is False
```

- [ ] **Step 3: Implement adapter (fixture mode + httpx hooks)**

`src/media2text/core/platform/douyin/adapter.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import httpx

from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged


class DouyinAdapterV1:
    """Douyin API adapter. Replace parse bodies with real API responses."""

    def __init__(
        self,
        client: httpx.Client | None,
        *,
        fixture_root: Path | None = None,
    ):
        self._client = client
        self._fixture_root = fixture_root

    def is_live(self, *, sec_uid: str, room_id: str) -> bool:
        if self._fixture_root:
            data = json.loads((self._fixture_root / "is_live_true.json").read_text())
            # toggle by room_id in tests
            if room_id == "offline":
                data = json.loads((self._fixture_root / "is_live_false.json").read_text())
            return bool(data.get("data", {}).get("live_status"))
        if not self._client:
            raise AuthRequired("no session")
        # TODO: real endpoint — implement when capturing traffic
        raise ParseFailed("is_live not implemented for live HTTP yet")

    def resolve_stream_url(self, *, room_id: str) -> str:
        if self._fixture_root:
            data = json.loads((self._fixture_root / "is_live_true.json").read_text())
            url = data.get("data", {}).get("stream_url")
            if not url:
                raise ParseFailed("missing stream_url in fixture")
            return url
        raise ParseFailed("resolve_stream_url not implemented for live HTTP yet")
```

> **Implementer note:** Before marking P1 done, replace stub parsers with real Douyin live-room API calls (reference DouyinLiveRecorder / jiji262). Keep fixture tests so CI stays offline.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_douyin_adapter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/platform/douyin/ tests/unit/test_douyin_adapter.py
git commit -m "feat: DouyinAdapterV1 skeleton with offline fixtures"
```

---

### Task 9: ffmpeg recorder (temp flv → remux mp4)

**Files:**
- Create: `src/media2text/core/ffmpeg.py`
- Test: `tests/unit/test_ffmpeg_remux.py`

- [ ] **Step 1: Write failing remux test** (mock subprocess)

`tests/unit/test_ffmpeg_remux.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.ffmpeg import remux_to_mp4


@patch("media2text.core.ffmpeg.subprocess.run")
def test_remux_calls_ffmpeg(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "a.flv"
    src.write_bytes(b"fake")
    dst = tmp_path / "out.mp4"
    remux_to_mp4(ffmpeg="ffmpeg", src=src, dst=dst)
    assert mock_run.called
    assert mock_run.call_args[0][0][0] == "ffmpeg"
```

- [ ] **Step 2: Implement**

`src/media2text/core/ffmpeg.py`:
```python
import subprocess
from pathlib import Path


def record_stream_copy(
    *,
    ffmpeg: str,
    stream_url: str,
    output_path: Path,
) -> subprocess.Popen:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        stream_url,
        "-c",
        "copy",
        "-f",
        "flv",
        str(output_path),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def stop_process(proc: subprocess.Popen, *, timeout: int = 30) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def remux_to_mp4(*, ffmpeg: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(src), "-c", "copy", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError("remux produced empty file")
```

- [ ] **Step 3: Run tests + commit**

```bash
pytest tests/unit/test_ffmpeg_remux.py -v
git add src/media2text/core/ffmpeg.py tests/unit/test_ffmpeg_remux.py
git commit -m "feat: ffmpeg record copy and remux helpers"
```

---

### Task 10: Process lock + live session repo

**Files:**
- Create: `src/media2text/core/process_lock.py`, extend `repos.py` for `LiveSessionRepo`
- Test: `tests/unit/test_process_lock.py`

- [ ] **Step 1: Lock file**

`src/media2text/core/process_lock.py`:
```python
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)
```

- [ ] **Step 2: LiveSessionRepo** — add CRUD for `live_sessions` table (stale cleanup, update pid/status)

- [ ] **Step 3: Tests + commit**

```bash
pytest tests/unit/test_process_lock.py -v
git commit -m "feat: workspace lock and live session repository"
```

---

### Task 11: LiveWatcher daemon loop

**Files:**
- Create: `src/media2text/core/platform/douyin/live.py` (watcher class), `src/media2text/cli/live.py`

- [ ] **Step 1: `LiveWatcher` class** — poll creators with `watch_live=1`, start/stop ffmpeg, remux on end, update DB

Pseudo-flow:
```python
class LiveWatcher:
    def run_once(self): ...  # single poll cycle
    def run_daemon(self): ...  # loop sleep poll_interval_sec
    def cleanup_stale(self): ...  # dead PIDs → failed
```

- [ ] **Step 2: CLI**

```bash
media2text live watch --daemon --json
media2text live watch --creator <id>   # optional filter
```

- [ ] **Step 3: Manual P1 gate**

1. `media2text doctor --json` → ok
2. `media2text auth login`
3. `media2text creator add '<douyin live or profile url>' --watch-live`
4. `media2text live watch --daemon`
5. Verify `data/creators/{sec_uid}/live/*.mp4` after stream ends

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: live watch daemon with flv temp and mp4 remux"
```

**P1 gate:** One completed live recording in workspace.

---

### Task 12: Creator `add` / `list` + resolver

**Files:**
- Create: `src/media2text/core/platform/douyin/resolver.py`, `src/media2text/cli/creator.py`

- [ ] **Step 1: Resolver** — follow redirects with httpx; extract `sec_uid` from HTML/JSON (implement incrementally; unit test with saved HTML fixture)

- [ ] **Step 2: CLI `creator add/list/remove`**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: creator registry and URL resolver"
```

---

## Phase P2 — VOD sync + download + manifest

### Task 13: `catalog.sync` + `download.run`

- [ ] Implement `DouyinAdapterV1.list_awemes` + pagination
- [ ] `AwemeRepo` upsert + dedupe by `aweme_id`
- [ ] `download.run` with concurrency limit from config
- [ ] Tests with fixtures

### Task 14: `agent-manifest.json` writer

- [ ] `src/media2text/core/manifest.py` — build items from DB, atomic write
- [ ] Call after download/live/transcribe

**P2 gate:** `media2text creator sync <id> --json` then `download run` → mp4 files + manifest updated.

---

## Phase P3 — Transcribe

### Task 15: Whisper backend

- [ ] `pip install -e ".[transcribe]"` optional extra
- [ ] `WhisperBackend.transcribe(path)` → `TranscriptResult`
- [ ] Write `.transcript.json` + `.transcript.md`
- [ ] CLI `media2text transcribe path/`

**P3 gate:** Transcribe one short local mp4.

---

## Phase P4 — Pipeline + README

### Task 16: `pipeline run`

- [ ] `src/media2text/core/pipeline/runner.py` orchestrates sync → download → transcribe
- [ ] JSON summary with per-stage counts and `errors[]`
- [ ] README: Agent examples (`--json`, exit codes, `auth_required`)

---

## Phase P5 — CI hardening

### Task 17: GitHub Actions + real fixtures

- [ ] `.github/workflows/ci.yml` — ruff, pyright, pytest (exclude `live` marker)
- [ ] Capture real Douyin fixture files; expand adapter tests to ≥80% branch coverage on parser helpers
- [ ] `config.example.yaml` copied in README

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| G1 Agent CLI `--json` | Task 2, all CLI tasks |
| G2 Playwright login | Task 5 |
| G3 Creator registry | Task 12 |
| G4 Catalog dedupe | Task 13 |
| G5 VOD download | Task 13 |
| G6 Live watch | Tasks 8–11 |
| G7 Pluggable transcribe | Task 15 |
| G8 Pipeline | Task 16 |
| doctor | Task 6 |
| DouyinAdapterV1 | Tasks 7–8 |
| flv → remux | Task 9, 11 |
| httpx + PW fallback | Tasks 7–8 (HTTP parse TODO noted) |
| live process lock | Task 10 |
| agent-manifest | Task 14 |
| Exit codes 0–4 | Task 2 |
| P6 Bilibili | Out of scope |

**Placeholder scan:** Task 8 notes real Douyin HTTP parsing must be completed before P1 sign-off (intentional milestone, not TBD).

**Type consistency:** `LiveSession` uses `temp_path`, `status` includes `remuxing` per spec.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-05-20-media2text-douyin.md`.

**Two execution options:**

1. **Subagent-driven (recommended)** — one fresh subagent per task, review between tasks  
2. **Inline execution** — implement P0→P1 in this session with checkpoints after P0 and P1 gates

Which approach do you want?
