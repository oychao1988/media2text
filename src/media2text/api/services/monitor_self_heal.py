"""Monitor daemon self-heal for desktop serve / health loop."""

from __future__ import annotations

import time
from typing import Any

import structlog

from media2text.api.services.work_queue import recover_stale_work
from media2text.core.config import AppConfig
from media2text.core.runtime.monitor_lock import (
    clear_invalid_monitor_lock,
    is_monitor_watch_pid,
    monitor_effectively_running,
    read_lock_pid,
    read_lock_record,
)
from media2text.core.runtime.status import _live_poll_interval_sec
from media2text.core.runtime.supervisor import MonitorSupervisor

log = structlog.get_logger()
_last_heal_at: float = 0.0
_heal_timestamps: list[float] = []
_HOURLY_WINDOW_SEC = 3600.0


def _hourly_limit_reached(desktop, now: float) -> bool:
    max_per_hour = desktop.monitor_self_heal_max_per_hour
    _heal_timestamps[:] = [t for t in _heal_timestamps if now - t < _HOURLY_WINDOW_SEC]
    return len(_heal_timestamps) >= max_per_hour


def maybe_self_heal_monitor(
    cfg: AppConfig,
    supervisor: MonitorSupervisor,
    *,
    force: bool = False,
) -> dict[str, Any]:
    global _last_heal_at
    desktop = cfg.desktop
    if not desktop.auto_start_monitor or not desktop.monitor_self_heal:
        return {"ok": True, "healed": False, "skipped": "disabled"}

    ws = cfg.ensure_workspace()
    lock_path = ws / ".monitor-watch.lock"
    live_poll = _live_poll_interval_sec(cfg)
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status=supervisor.status_dict(cfg), live_poll_sec=live_poll
    )
    if running:
        return {"ok": True, "healed": False, "running": True}

    now = time.monotonic()
    if not force and (now - _last_heal_at) < desktop.monitor_self_heal_cooldown_sec:
        return {"ok": True, "healed": False, "skipped": "cooldown", "reason": reason}
    if _hourly_limit_reached(desktop, now):
        log.warning("monitor_self_heal_gave_up", reason=reason)
        return {"ok": True, "healed": False, "skipped": "hourly_limit", "reason": reason}

    if reason == "heartbeat_stale":
        record = read_lock_record(lock_path)
        lock_pid = record.pid if record is not None else read_lock_pid(lock_path)
        if (
            record is not None
            and record.mode == "external"
            and lock_pid
            and is_monitor_watch_pid(lock_pid)
        ):
            recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
            return {
                "ok": True,
                "healed": False,
                "skipped": "external_heartbeat_stale",
                "pid": lock_pid,
                "reason": reason,
            }

    sup_status = supervisor.status_dict(cfg)
    if sup_status.get("thread_alive") and reason == "embedded_thread_dead":
        repair = supervisor.repair_embedded_lock(cfg)
        if repair.get("ok"):
            running, _ = monitor_effectively_running(
                ws,
                cfg,
                supervisor_status=sup_status,
                live_poll_sec=live_poll,
            )
            if running:
                recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
                _last_heal_at = now
                _heal_timestamps.append(now)
                log.info("monitor_self_heal_ok", reason=reason, action="repair_embedded_lock")
                return {
                    "ok": True,
                    "healed": True,
                    "reason": reason,
                    "repair": repair,
                }

    clear_invalid_monitor_lock(lock_path)
    pid = read_lock_pid(lock_path)
    if pid and is_monitor_watch_pid(pid):
        return {"ok": True, "healed": False, "skipped": "external_started", "pid": pid, "reason": reason}

    result = supervisor.takeover(cfg)
    if not result.get("ok") and reason == "lock_pid_mismatch":
        clear_invalid_monitor_lock(lock_path)
        result = supervisor.takeover(cfg)

    if result.get("ok"):
        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
        _last_heal_at = now
        _heal_timestamps.append(now)
        log.info("monitor_self_heal_ok", reason=reason)
        return {"ok": True, "healed": True, "reason": reason, "takeover": result}

    log.warning("monitor_self_heal_failed", reason=reason, detail=result)
    return {"ok": False, "healed": False, "reason": reason, "takeover": result}
