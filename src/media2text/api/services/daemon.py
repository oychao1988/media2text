"""Monitor watch daemon control for desktop API."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from media2text.core.archive.health import monitor_lock_pid
from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.storage.repos import LiveSessionRepo, PostProcessJobRepo
from media2text.core.workspace import open_db

LOG_NAME = "monitor-watch.log"


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
        active = LiveSessionRepo(conn).list_active()
    finally:
        conn.close()
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
    root = Path(__file__).resolve().parents[4]
    proc = subprocess.Popen(
        [sys.executable, "-m", "media2text", "monitor", "watch", "--daemon"],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "spawned": True, "pid": proc.pid}


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
