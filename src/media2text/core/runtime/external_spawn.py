"""Spawn CLI ``monitor watch --daemon`` as a detached external process."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Any

import structlog

from media2text.core.archive.health import monitor_lock_pid
from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import _pid_alive

log = structlog.get_logger()

_SPAWN_WAIT_SEC = 15.0


def _monitor_daemon_cmd() -> list[str]:
    bin_path = shutil.which("media2text")
    if bin_path:
        return [bin_path, "monitor", "watch", "--daemon"]
    return [sys.executable, "-m", "media2text", "monitor", "watch", "--daemon"]


def spawn_cli_monitor_daemon(
    cfg: AppConfig,
    *,
    creator_id: str | None = None,
    wait_sec: float = _SPAWN_WAIT_SEC,
) -> dict[str, Any]:
    """Start external monitor watch; return lock PID when ready."""
    ws = cfg.ensure_workspace()
    lock_path = ws / ".monitor-watch.lock"
    existing = monitor_lock_pid(ws)
    if existing and _pid_alive(existing) and existing != os.getpid():
        return {
            "ok": False,
            "already_running_external": True,
            "pid": existing,
            "error": "external monitor watch daemon already running",
        }

    log_path = ws / "monitor-watch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = _monitor_daemon_cmd()
    if creator_id:
        cmd.extend(["--creator", creator_id])
    env = os.environ.copy()
    try:
        log_fd = open(log_path, "a", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": "log_open_failed", "detail": str(exc)}
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
    except OSError as exc:
        log_fd.close()
        return {"ok": False, "error": "spawn_failed", "detail": str(exc)}
    finally:
        try:
            log_fd.close()
        except OSError:
            pass

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        pid = monitor_lock_pid(ws)
        if pid and _pid_alive(pid) and pid != os.getpid():
            log.info("monitor_external_spawned", pid=pid, spawn_pid=proc.pid)
            return {
                "ok": True,
                "managed_by": "external",
                "pid": pid,
                "spawn_pid": proc.pid,
                "lock_path": str(lock_path),
            }
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": "spawn_exited_early",
                "exit_code": proc.returncode,
                "spawn_pid": proc.pid,
            }
        time.sleep(0.25)

    return {
        "ok": False,
        "error": "spawn_timeout",
        "spawn_pid": proc.pid,
        "message": "终端守护进程未能及时写入锁文件",
    }
