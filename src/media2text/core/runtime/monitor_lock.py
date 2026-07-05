"""Trusted monitor-watch lock validation and effective-running checks."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from media2text.core.runtime.heartbeat import _age_sec, heartbeat_stale_sec, read_heartbeat

LockReason = Literal[
    "lock_missing",
    "lock_pid_mismatch",
    "heartbeat_stale",
    "embedded_thread_dead",
]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_commandline(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    return line or None


def is_monitor_watch_pid(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if not _pid_alive(pid):
        return False
    cmd = _process_commandline(pid) or ""
    lowered = cmd.lower()
    if "media2text" not in lowered:
        return False
    return "monitor" in lowered and "watch" in lowered


def is_embedded_monitor_pid(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if not _pid_alive(pid):
        return False
    cmd = _process_commandline(pid) or ""
    lowered = cmd.lower()
    if "media2text" not in lowered:
        return False
    return "serve" in lowered


def is_trusted_monitor_lock_pid(pid: int | None) -> bool:
    return is_monitor_watch_pid(pid) or is_embedded_monitor_pid(pid)


def read_lock_pid(lock_path: Path) -> int | None:
    record = read_lock_record(lock_path)
    return record.pid if record is not None else None


def read_lock_record(lock_path: Path) -> LockRecord | None:
    if not lock_path.is_file():
        return None
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            pid = int(data["pid"])
            mode = str(data.get("mode") or "external")
            argv = str(data.get("argv") or LockRecord(pid=pid, mode=mode).argv)
            return LockRecord(pid=pid, mode=mode, argv=argv)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
    try:
        return LockRecord(pid=int(raw), mode="external")
    except ValueError:
        return None


@dataclass(frozen=True)
class LockRecord:
    pid: int
    mode: str = "external"
    argv: str = "media2text monitor watch --daemon"


def write_lock_record(lock_path: Path, *, pid: int, mode: str = "external") -> None:
    payload = LockRecord(pid=pid, mode=mode)
    lock_path.write_text(
        json.dumps({"pid": payload.pid, "mode": payload.mode, "argv": payload.argv}),
        encoding="utf-8",
    )


def clear_invalid_monitor_lock(lock_path: Path) -> bool:
    record = read_lock_record(lock_path)
    if record is None:
        if lock_path.is_file():
            lock_path.unlink(missing_ok=True)
            return True
        return False
    if not _pid_alive(record.pid):
        lock_path.unlink(missing_ok=True)
        return True
    if record.mode == "embedded" and is_embedded_monitor_pid(record.pid):
        return False
    if not is_trusted_monitor_lock_pid(record.pid):
        lock_path.unlink(missing_ok=True)
        return True
    return False


def embedded_heartbeat_stale_sec(cfg, live_poll_sec: int) -> float:
    """Embedded monitor may hold heartbeat during a full live-probe round (Playwright)."""
    from media2text.core.live.probe import probe_budget_sec
    from media2text.core.storage.repos import CreatorRepo
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    try:
        n = sum(
            1
            for c in CreatorRepo(conn).list_monitored()
            if c.platform in ("douyin", "bilibili")
        )
    finally:
        conn.close()
    probe_budget = probe_budget_sec(cfg, max(1, n))
    return max(heartbeat_stale_sec(live_poll_sec), probe_budget + live_poll_sec)


def monitor_effectively_running(
    workspace: Path,
    cfg,
    *,
    supervisor_status: dict[str, Any] | None,
    live_poll_sec: int,
) -> tuple[bool, str | None]:
    sup = supervisor_status or {}
    lock_path = workspace / ".monitor-watch.lock"
    lock_pid = read_lock_pid(lock_path)
    stale_sec = (
        embedded_heartbeat_stale_sec(cfg, live_poll_sec)
        if sup.get("thread_alive")
        else heartbeat_stale_sec(live_poll_sec)
    )

    if sup.get("thread_alive"):
        if lock_pid != os.getpid():
            return False, "embedded_thread_dead"
        heartbeat = read_heartbeat(workspace)
        last_tick = heartbeat.get("last_tick_at") if heartbeat else None
        tick_age = _age_sec(last_tick)
        if tick_age is None or tick_age > stale_sec:
            return False, "heartbeat_stale"
        return True, None

    if lock_pid is None:
        return False, "lock_missing"

    record = read_lock_record(lock_path)
    if record is not None and record.mode == "embedded":
        if not is_embedded_monitor_pid(lock_pid):
            return False, "lock_pid_mismatch"
    elif not is_monitor_watch_pid(lock_pid):
        return False, "lock_pid_mismatch"

    heartbeat = read_heartbeat(workspace)
    last_tick = heartbeat.get("last_tick_at") if heartbeat else None
    tick_age = _age_sec(last_tick)
    if tick_age is None or tick_age > stale_sec:
        return False, "heartbeat_stale"

    return True, None
