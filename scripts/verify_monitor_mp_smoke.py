#!/usr/bin/env python3
"""Run automated MP-smoke checks (TODOS.md Monitor DB Contention / Hardening)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit/test_monitor_mp_smoke.py",
        "-v",
        "--tb=short",
        "-q",
    ]
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode == 0:
        print("verify_monitor_mp_smoke: ok (4 scenarios)", flush=True)
    else:
        print("verify_monitor_mp_smoke: failed", file=sys.stderr, flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
