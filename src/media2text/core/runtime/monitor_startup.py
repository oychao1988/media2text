"""Single-owner monitor startup — detect existing owner before embedded/external start."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import structlog

from media2text.core.config import AppConfig
from media2text.core.process_lock import clear_stale_workspace_lock
from media2text.core.runtime.heartbeat import read_heartbeat, _age_sec
from media2text.core.runtime.monitor_lock import (
    clear_invalid_monitor_lock,
    embedded_heartbeat_stale_sec,
    is_embedded_monitor_pid,
    is_monitor_watch_pid,
    monitor_effectively_running,
    read_lock_pid,
)

log = structlog.get_logger()

ManagedBy = Literal["none", "embedded", "external"]


def clear_orphan_embedded_lock(
    lock_path: Path,
    supervisor: Any | None = None,
) -> bool:
    """Drop embedded lock when this serve process holds it but monitor thread is gone."""
    if not lock_path.is_file():
        return False
    pid = read_lock_pid(lock_path)
    if pid is None or pid != os.getpid():
        return False
    if supervisor is not None and supervisor._is_embedded_running():
        return False
    lock_path.unlink(missing_ok=True)
    log.info("monitor_orphan_embedded_lock_cleared", pid=pid)
    return True


def monitor_owner_status(
    cfg: AppConfig,
    supervisor: Any | None = None,
) -> dict[str, Any]:
    """Return whether a monitor owner is active and who holds the lock."""
    if supervisor is not None and supervisor._is_embedded_running():
        return {"running": True, "managed_by": "embedded", "pid": os.getpid()}

    lock_path = cfg.ensure_workspace() / ".monitor-watch.lock"
    clear_invalid_monitor_lock(lock_path)
    clear_orphan_embedded_lock(lock_path, supervisor)
    pid = read_lock_pid(lock_path)
    if pid is None:
        return {"running": False, "managed_by": "none", "pid": None}

    if is_embedded_monitor_pid(pid):
        if pid == os.getpid():
            return {"running": False, "managed_by": "none", "pid": None}
        return {"running": True, "managed_by": "embedded", "pid": pid}
    if is_monitor_watch_pid(pid):
        return {"running": True, "managed_by": "external", "pid": pid}

    return {"running": False, "managed_by": "none", "pid": None}


def assert_monitor_slot_available(cfg: AppConfig) -> dict[str, Any] | None:
    """CLI/external start: return error payload when another owner is active."""
    owner = monitor_owner_status(cfg)
    if not owner["running"]:
        return None
    managed_by = owner["managed_by"]
    return {
        "ok": False,
        "already_running": True,
        "managed_by": managed_by,
        "pid": owner["pid"],
        "error": f"monitor already running ({managed_by})",
    }


def auto_start_embedded_monitor(
    cfg: AppConfig,
    supervisor: Any,
    *,
    recover_stale: bool = True,
) -> dict[str, Any]:
    """Desktop serve startup: start embedded monitor only when no owner is active."""
    owner = monitor_owner_status(cfg, supervisor)
    if owner["running"]:
        log.info(
            "monitor_auto_start_skipped",
            managed_by=owner["managed_by"],
            pid=owner["pid"],
        )
        return {
            "ok": True,
            "skipped": True,
            "already_running": True,
            "managed_by": owner["managed_by"],
            "pid": owner["pid"],
        }

    result = supervisor.start(cfg)
    if result.get("already_running") or result.get("already_running_external"):
        managed_by: ManagedBy = (
            "external" if result.get("already_running_external") else "embedded"
        )
        log.info("monitor_auto_start_skipped", managed_by=managed_by, detail=result)
        return {
            "ok": True,
            "skipped": True,
            "already_running": True,
            "managed_by": managed_by,
            "pid": result.get("pid"),
        }
    if result.get("already_running_embedded"):
        log.info("monitor_auto_start_skipped", managed_by="embedded", detail=result)
        return {
            "ok": True,
            "skipped": True,
            "already_running": True,
            "managed_by": "embedded",
            "pid": result.get("pid"),
        }

    if recover_stale and result.get("ok"):
        from media2text.api.services.work_queue import recover_stale_work

        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
    elif not result.get("ok"):
        log.warning("monitor_auto_start_failed", detail=result)
    return result


def prepare_embedded_monitor_startup(
    cfg: AppConfig,
    supervisor: Any,
    *,
    recover_stale: bool = True,
) -> dict[str, Any]:
    """Startup recovery: clean stale locks, restart stuck embedded, start if needed."""
    ws = cfg.ensure_workspace()
    lock_path = ws / ".monitor-watch.lock"

    clear_stale_workspace_lock(ws / ".serve.lock")
    clear_invalid_monitor_lock(lock_path)
    clear_orphan_embedded_lock(lock_path, supervisor)

    if not cfg.desktop.auto_start_monitor:
        return {"ok": True, "skipped": "auto_start_disabled"}

    owner = monitor_owner_status(cfg, supervisor)
    if owner["running"] and owner["managed_by"] == "external":
        log.info("monitor_startup_skipped_external", pid=owner["pid"])
        return {
            "ok": True,
            "skipped": True,
            "already_running": True,
            "managed_by": "external",
            "pid": owner["pid"],
        }

    from media2text.core.runtime.status import _live_poll_interval_sec

    live_poll = _live_poll_interval_sec(cfg)
    sup_status = supervisor.status_dict(cfg)
    running, reason = monitor_effectively_running(
        ws,
        cfg,
        supervisor_status=sup_status,
        live_poll_sec=live_poll,
    )
    if running:
        log.info("monitor_startup_already_healthy")
        if recover_stale:
            from media2text.api.services.work_queue import recover_stale_work

            recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
        return {
            "ok": True,
            "skipped": True,
            "already_running": True,
            "managed_by": "embedded",
        }

    if sup_status.get("thread_alive"):
        heartbeat = read_heartbeat(ws)
        last_tick = heartbeat.get("last_tick_at") if heartbeat else None
        tick_age = _age_sec(last_tick)
        stale_limit = embedded_heartbeat_stale_sec(cfg, live_poll)
        if tick_age is not None and tick_age < stale_limit:
            log.info(
                "monitor_startup_probe_in_progress",
                tick_age_sec=tick_age,
                stale_limit_sec=stale_limit,
            )
            return {
                "ok": True,
                "skipped": True,
                "already_running": True,
                "managed_by": "embedded",
                "probe_in_progress": True,
            }
        log.info("monitor_startup_restart_stuck_embedded", reason=reason)
        result = supervisor.takeover(cfg)
    elif reason in ("heartbeat_stale", "embedded_thread_dead", "lock_pid_mismatch"):
        log.info("monitor_startup_clear_stale_state", reason=reason)
        clear_invalid_monitor_lock(lock_path)
        clear_orphan_embedded_lock(lock_path, supervisor)
        result = supervisor.start(cfg)
    else:
        return auto_start_embedded_monitor(cfg, supervisor, recover_stale=recover_stale)

    if recover_stale and result.get("ok"):
        from media2text.api.services.work_queue import recover_stale_work

        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
    elif not result.get("ok"):
        log.warning("monitor_startup_failed", detail=result)
    return result
