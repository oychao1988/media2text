"""Monitor watch daemon control for desktop API."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from media2text.core.archive.health import monitor_lock_pid
from media2text.core.process_lock import clear_stale_workspace_lock
from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.storage.repos import (
    LiveSessionRepo,
    MonitorTaskRepo,
    PostProcessJobRepo,
)
from media2text.core.workspace import open_db

LOG_NAME = "monitor-watch.log"
STARTUP_WAIT_SEC = 8.0
STARTUP_POLL_SEC = 0.5


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def daemon_status(cfg: AppConfig) -> dict:
    ws = cfg.ensure_workspace()
    pid = monitor_lock_pid(ws)
    running = bool(pid and _pid_alive(pid))
    conn = open_db(cfg)
    try:
        jobs = PostProcessJobRepo(conn)
        counts = jobs.count_by_status()
        task_counts = MonitorTaskRepo(conn).count_by_status()
        active = LiveSessionRepo(conn).list_active()
    finally:
        conn.close()
    failed_tasks = task_counts.get("failed", 0)
    return {
        "running": running,
        "pid": pid if running else None,
        "lock_pid": pid,
        "live_tick_interval_sec": cfg.live.live_poll_interval_sec,
        "post_process": {
            "max_workers": resolve_post_process_workers(cfg),
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
        },
        "monitor_tasks": {
            "pending": task_counts.get("pending", 0),
            "running": task_counts.get("running", 0),
            "failed": failed_tasks,
            "dlq": failed_tasks,
        },
        "active_recordings": len(active),
        "log_path": str(ws / LOG_NAME),
    }


def read_daemon_logs(cfg: AppConfig, *, tail: int = 5) -> dict:
    ws = cfg.ensure_workspace()
    log_path = ws / LOG_NAME
    if not log_path.is_file():
        return {"ok": True, "lines": [], "path": str(log_path)}
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(log_path), "lines": []}
    lines = text.splitlines()
    n = max(1, min(tail, 500))
    return {"ok": True, "path": str(log_path), "lines": lines[-n:]}


def _remove_stale_lock(ws: Path) -> bool:
    return clear_stale_workspace_lock(ws / ".monitor-watch.lock")


def _python_executable(root: Path) -> str:
    candidates = [
        root / ".venv" / "bin" / "python3",
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def start_daemon(cfg: AppConfig) -> dict:
    ws = cfg.ensure_workspace()
    pid = monitor_lock_pid(ws)
    if pid and _pid_alive(pid):
        return {
            "ok": False,
            "already_running": True,
            "pid": pid,
            "error": "monitor watch daemon already running",
        }
    stale_removed = _remove_stale_lock(ws)
    root = Path(__file__).resolve().parents[4]
    log_path = ws / LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    python_exe = _python_executable(root)
    log_fd = log_path.open("a", encoding="utf-8")
    try:
        subprocess.Popen(
            [python_exe, "-m", "media2text", "monitor", "watch", "--daemon"],
            cwd=str(root),
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fd.close()
    deadline = time.monotonic() + STARTUP_WAIT_SEC
    while time.monotonic() < deadline:
        pid = monitor_lock_pid(ws)
        if pid and _pid_alive(pid):
            return {
                "ok": True,
                "spawned": True,
                "pid": pid,
                "stale_lock_removed": stale_removed,
            }
        time.sleep(STARTUP_POLL_SEC)
    tail = read_daemon_logs(cfg, tail=3).get("lines") or []
    return {
        "ok": False,
        "error": "monitor watch daemon failed to start",
        "stale_lock_removed": stale_removed,
        "log_tail": tail,
    }


def stop_daemon(cfg: AppConfig) -> dict:
    ws = cfg.ensure_workspace()
    pid = monitor_lock_pid(ws)
    if not pid:
        return {"ok": True, "stopped": False, "message": "daemon not running"}
    if not _pid_alive(pid):
        lock = ws / ".monitor-watch.lock"
        lock.unlink(missing_ok=True)
        return {"ok": True, "stopped": False, "stale_lock_removed": True, "pid": pid}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "pid": pid}
    return {"ok": True, "stopped": True, "pid": pid}
