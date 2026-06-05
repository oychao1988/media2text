"""Embedded monitor watch supervisor for ``media2text serve``."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from media2text.core.archive.health import monitor_lock_pid
from media2text.core.config import AppConfig
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.process_lock import (
    LockError,
    acquire_workspace_lock,
    release_workspace_lock,
)
from media2text.core.runtime.status import write_heartbeat

log = structlog.get_logger()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@dataclass
class SupervisorStatus:
    running: bool
    managed_by: str
    thread_alive: bool
    started_at: str | None
    last_tick_at: str | None
    pid: int | None


class MonitorSupervisor:
    """Thread-hosted monitor watch; safe to run inside serve process."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock_fd: int | None = None
        self._lock_path: Path | None = None
        self._cfg: AppConfig | None = None
        self._creator_id: str | None = None
        self._started_at: str | None = None
        self._last_tick_at: str | None = None
        self._state_lock = threading.Lock()

    def record_tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._state_lock:
            self._last_tick_at = now
        if self._cfg is not None:
            write_heartbeat(self._cfg.ensure_workspace(), last_tick_at=now)

    def start(self, cfg: AppConfig, *, creator_id: str | None = None) -> dict[str, Any]:
        ws = cfg.ensure_workspace()
        lock_path = ws / ".monitor-watch.lock"
        pid = monitor_lock_pid(ws)
        if pid and _pid_alive(pid) and not self._holds_embedded_lock(pid):
            return {
                "ok": False,
                "already_running_external": True,
                "pid": pid,
                "error": "external monitor watch daemon already running",
            }
        if self._thread is not None and self._thread.is_alive():
            return {
                "ok": False,
                "already_running": True,
                "error": "embedded monitor supervisor already running",
            }

        self._cfg = cfg
        self._creator_id = creator_id
        self._stop_event = threading.Event()
        try:
            self._lock_fd = acquire_workspace_lock(lock_path)
        except LockError as exc:
            ext_pid = monitor_lock_pid(ws)
            if ext_pid and _pid_alive(ext_pid):
                return {
                    "ok": False,
                    "already_running_external": True,
                    "pid": ext_pid,
                    "error": str(exc),
                }
            return {"ok": False, "error": str(exc)}
        self._lock_path = lock_path
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(
            target=self._run_daemon_thread,
            name="monitor-supervisor",
            daemon=True,
        )
        self._thread.start()
        log.info("monitor_supervisor_started", creator_id=creator_id)
        return {"ok": True, "managed_by": "embedded", "started_at": self._started_at}

    def stop(
        self,
        cfg: AppConfig | None = None,
        *,
        timeout_sec: float = 10.0,
    ) -> dict[str, Any]:
        check_cfg = cfg or self._cfg
        if not self._is_embedded_running():
            if self._lock_fd is not None:
                self._release_lock()
                return {
                    "ok": True,
                    "stopped": True,
                    "managed_by": "embedded",
                    "message": "embedded supervisor already stopped",
                }
            ext_pid = None
            if check_cfg is not None:
                ext_pid = monitor_lock_pid(check_cfg.ensure_workspace())
            if ext_pid and _pid_alive(ext_pid):
                return {
                    "ok": False,
                    "not_owner": True,
                    "pid": ext_pid,
                    "error": "monitor managed by external process",
                }
            return {"ok": True, "stopped": False, "message": "embedded supervisor not running"}

        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_sec)
            if thread.is_alive():
                log.warning("monitor_supervisor_stop_timeout", timeout_sec=timeout_sec)
                return {
                    "ok": False,
                    "stopped": False,
                    "error": "stop_timeout",
                    "message": "监控线程仍在退出中，请稍候再试",
                }
        self._thread = None
        self._release_lock()
        self._reset_stale_queue_work(check_cfg)
        log.info("monitor_supervisor_stopped")
        return {"ok": True, "stopped": True, "managed_by": "embedded"}

    def status(self, cfg: AppConfig) -> SupervisorStatus:
        ws = cfg.ensure_workspace()
        lock_pid = monitor_lock_pid(ws)
        thread_alive = self._thread is not None and self._thread.is_alive()
        if thread_alive:
            managed_by = "embedded"
            running = True
            pid = os.getpid()
        elif lock_pid and _pid_alive(lock_pid):
            managed_by = "external"
            running = True
            pid = lock_pid
        else:
            managed_by = "none"
            running = False
            pid = None
        with self._state_lock:
            started_at = self._started_at
            last_tick_at = self._last_tick_at
        return SupervisorStatus(
            running=running,
            managed_by=managed_by,
            thread_alive=thread_alive,
            started_at=started_at,
            last_tick_at=last_tick_at,
            pid=pid,
        )

    def status_dict(self, cfg: AppConfig) -> dict[str, Any]:
        s = self.status(cfg)
        return {
            "running": s.running,
            "managed_by": s.managed_by,
            "thread_alive": s.thread_alive,
            "started_at": s.started_at,
            "last_tick_at": s.last_tick_at,
            "pid": s.pid,
        }

    def _is_embedded_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _holds_embedded_lock(self, pid: int) -> bool:
        return pid == os.getpid() and self._lock_fd is not None

    def _run_daemon_thread(self) -> None:
        cfg = self._cfg
        if cfg is None:
            return
        watcher: MonitorWatcher | None = None
        try:
            watcher = MonitorWatcher(cfg)
            watcher._run_daemon_locked(
                creator_id=self._creator_id,
                on_live_tick=self.record_tick,
                stop_event=self._stop_event,
            )
        except Exception as exc:
            log.exception(
                "monitor_supervisor_thread_failed",
                error=str(exc),
            )
        finally:
            if watcher is not None:
                try:
                    watcher._conn.close()
                except Exception:
                    pass
            self._release_lock()
            self._thread = None

    def _reset_stale_queue_work(self, cfg: AppConfig | None) -> None:
        if cfg is None:
            return
        from media2text.core.storage.repos import MonitorTaskRepo, PostProcessJobRepo
        from media2text.core.workspace import open_db

        conn = open_db(cfg)
        try:
            MonitorTaskRepo(conn).reset_stale_running(older_than_sec=1)
            PostProcessJobRepo(conn).reset_stale_running(older_than_sec=1)
        finally:
            conn.close()

    def _release_lock(self) -> None:
        if self._lock_path is not None:
            release_workspace_lock(self._lock_path, self._lock_fd)
        self._lock_fd = None
        self._lock_path = None
