"""Single-owner media2text serve startup — detect and resolve conflicting sidecars."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any

import structlog

from media2text.core.config import AppConfig
from media2text.core.process_lock import clear_stale_workspace_lock
from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock

log = structlog.get_logger()

_SERVE_STOP_TIMEOUT_SEC = 10.0


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


def is_media2text_serve_pid(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if not _pid_alive(pid):
        return False
    cmd = _process_commandline(pid) or ""
    lowered = cmd.lower()
    if "media2text" not in lowered:
        return False
    return "serve" in lowered


def list_media2text_serve_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "media2text.*serve"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        token = line.strip().split(None, 1)[0]
        try:
            pid = int(token)
        except ValueError:
            continue
        if is_media2text_serve_pid(pid):
            pids.append(pid)
    return sorted(set(pids))


def pids_on_port(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for token in result.stdout.split():
        try:
            pids.append(int(token))
        except ValueError:
            continue
    return pids


def stop_serve_pid(pid: int, *, timeout_sec: float = _SERVE_STOP_TIMEOUT_SEC) -> bool:
    if not is_media2text_serve_pid(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return not _pid_alive(pid)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.25)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return not _pid_alive(pid)
    time.sleep(0.25)
    return not _pid_alive(pid)


def _read_serve_lock_pid(lock_path) -> int | None:
    if not lock_path.is_file():
        return None
    try:
        return int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def resolve_serve_conflicts(
    cfg: AppConfig,
    port: int,
    *,
    managed: bool,
    own_pid: int | None = None,
) -> dict[str, Any]:
    """Resolve duplicate ``media2text serve`` before binding the API port."""
    own = own_pid or os.getpid()
    ws = cfg.ensure_workspace()
    lock_path = ws / ".serve.lock"
    monitor_lock_path = ws / ".monitor-watch.lock"

    clear_stale_workspace_lock(lock_path)
    others = [pid for pid in list_media2text_serve_pids() if pid != own]
    port_pids = [pid for pid in pids_on_port(port) if pid != own]

    if managed:
        to_kill = sorted(set(others))
        killed: list[int] = []
        for pid in to_kill:
            if stop_serve_pid(pid):
                killed.append(pid)
        clear_stale_workspace_lock(lock_path)
        clear_invalid_monitor_lock(monitor_lock_path)
        if killed:
            log.info("serve_conflicts_resolved", killed=killed, port=port, managed=True)
        return {"ok": True, "killed": killed, "managed": True}

    lock_pid = _read_serve_lock_pid(lock_path)
    alive_others = [pid for pid in others if _pid_alive(pid)]
    if alive_others:
        blocking = alive_others[0]
        return {
            "ok": False,
            "already_running": True,
            "pid": blocking,
            "error": f"media2text serve already running (PID {blocking})",
        }
    if lock_pid is not None and lock_pid != own and _pid_alive(lock_pid):
        return {
            "ok": False,
            "already_running": True,
            "pid": lock_pid,
            "error": f"media2text serve already running (PID {lock_pid})",
        }
    if port_pids:
        blocking = port_pids[0]
        return {
            "ok": False,
            "already_running": True,
            "pid": blocking,
            "error": f"port {port} already in use (PID {blocking})",
        }
    return {"ok": True, "killed": [], "managed": False}
