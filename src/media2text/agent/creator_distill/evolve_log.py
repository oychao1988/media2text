"""Append-only evolve audit log (Hermes §24.4.3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def evolve_log_path(profile_dir: Path) -> Path:
    return profile_dir / "evolve-log.jsonl"


def append_evolve_log(profile_dir: Path, entry: dict[str, Any]) -> None:
    path = evolve_log_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_evolve_log(
    profile_dir: Path,
    *,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    path = evolve_log_path(profile_dir)
    if not path.is_file():
        return [], 0
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return [], 0
    total = len(rows)
    page = rows[offset : offset + limit] if offset < total else []
    return page, total
