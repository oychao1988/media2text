from __future__ import annotations

import sqlite3
from pathlib import Path

from media2text.core.archive.indexer import _collect_transcript_paths


def monitor_lock_pid(workspace: Path) -> int | None:
    from media2text.core.runtime.monitor_lock import read_lock_pid

    return read_lock_pid(workspace / ".monitor-watch.lock")


def monitor_lock_valid(workspace: Path) -> bool:
    from media2text.core.runtime.monitor_lock import is_monitor_watch_pid, read_lock_pid

    pid = read_lock_pid(workspace / ".monitor-watch.lock")
    if pid is None:
        return True
    return is_monitor_watch_pid(pid)


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
