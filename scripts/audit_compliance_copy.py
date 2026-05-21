#!/usr/bin/env python3
"""Scan configured paths for banned investment-advice phrasing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_PATHS = [
    ROOT / "src/media2text/core/notify",
    ROOT / "README.md",
]

# Template / marketing wording that must not appear in product copy.
BANNED_PHRASES = [
    "荐股",
    "跟单",
    "买入建议",
    "卖出建议",
    "保证收益",
    "稳赚",
    "喊单",
    "带单",
]


def main() -> int:
    violations: list[str] = []
    for base in SCAN_PATHS:
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = sorted(base.rglob("*.py")) + sorted(base.rglob("*.md"))
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"skip {path}: {exc}", file=sys.stderr)
                continue
            for phrase in BANNED_PHRASES:
                if phrase in text:
                    violations.append(f"{path}: contains '{phrase}'")
    if violations:
        print("compliance copy audit failed:")
        for line in violations:
            print(f"  - {line}")
        return 1
    print("compliance copy audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
