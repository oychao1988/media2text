#!/usr/bin/env python3
"""Fail CI if live session mutations bypass StateWriter (R3b guard)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_FILES = [
    ROOT / "src/media2text/core/live/recording.py",
    ROOT / "src/media2text/core/platform/douyin/live.py",
    ROOT / "src/media2text/core/platform/bilibili/live.py",
]

WRITE_METHODS = (
    "set_offline_since",
    "clear_offline_since",
    "update_status",
    "update_recording_state",
    "clear_pid",
    "append_segment_path",
    "increment_reconnect_attempts",
    "mark_stale_recordings_failed",
    "create",
)

FORBIDDEN_PATTERNS = [
    (
        rf"(?<![\w.])_sessions\.({'|'.join(WRITE_METHODS)})\s*\(",
        "_sessions write",
    ),
    (
        rf"LiveSessionRepo\([^)]*\)\.({'|'.join(WRITE_METHODS)})\s*\(",
        "LiveSessionRepo write",
    ),
    (
        rf"(?<![\w.])sessions\.({'|'.join(WRITE_METHODS)})\s*\(",
        "sessions write",
    ),
    (r"(?<![\w.])refresh_manifest\s*\(", "refresh_manifest"),
]


def main() -> int:
    violations: list[str] = []
    for path in SCAN_FILES:
        if not path.is_file():
            violations.append(f"missing scan file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, name in FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_no}: {name}")
    if violations:
        print("Direct LiveSessionRepo writes found outside StateWriter:")
        for v in violations:
            print(f"  {v}")
        return 1
    print("OK: no direct live session repo writes in guarded files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
