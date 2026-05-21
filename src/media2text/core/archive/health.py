from __future__ import annotations

import sqlite3
from pathlib import Path

from media2text.core.archive.indexer import _collect_transcript_paths


def monitor_lock_pid(workspace: Path) -> int | None:
    lock = workspace / ".monitor-watch.lock"
    if not lock.is_file():
        return None
    try:
        raw = lock.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def is_index_stale(conn: sqlite3.Connection, workspace: Path) -> bool:
    """True when a transcript file on disk has no rows in transcript_segments."""
    for path in _collect_transcript_paths(conn, workspace, creator_id=None):
        row = conn.execute(
            "SELECT 1 FROM transcript_segments WHERE transcript_path = ? LIMIT 1",
            (str(path.resolve()),),
        ).fetchone()
        if not row:
            return True
    return False
