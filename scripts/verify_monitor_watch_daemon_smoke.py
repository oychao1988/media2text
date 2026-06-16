#!/usr/bin/env python3
"""Non-blocking smoke for monitor-watch-daemon.sh lock cleanup (SH-3 / #315)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock, read_lock_pid


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="m2t-daemon-smoke-") as td:
        lock_path = Path(td) / ".monitor-watch.lock"
        lock_path.write_text("581", encoding="utf-8")
        clear_invalid_monitor_lock(lock_path)
        pid = read_lock_pid(lock_path)
        if pid == 581 or (lock_path.is_file() and lock_path.read_text(encoding="utf-8").strip() == "581"):
            print("verify_monitor_watch_daemon_smoke: fake lock 581 was not cleared", file=sys.stderr)
            return 1
    print("verify_monitor_watch_daemon_smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
