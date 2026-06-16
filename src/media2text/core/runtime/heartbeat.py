"""Runtime heartbeat file helpers (shared by monitor lock and status)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HEARTBEAT_NAME = ".runtime-heartbeat"


def heartbeat_stale_sec(live_poll_sec: int) -> float:
    return max(90.0, 2 * live_poll_sec)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_sec(since: str | None) -> float | None:
    start = _parse_iso(since)
    if not start:
        return None
    return (datetime.now(timezone.utc) - start).total_seconds()


def read_heartbeat(workspace: Path) -> dict[str, Any] | None:
    path = workspace / HEARTBEAT_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_heartbeat(workspace: Path, *, last_tick_at: str) -> None:
    path = workspace / HEARTBEAT_NAME
    payload = {"last_tick_at": last_tick_at}
    path.write_text(json.dumps(payload), encoding="utf-8")
