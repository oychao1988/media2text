"""Desktop runtime API service (embedded MonitorSupervisor)."""

from __future__ import annotations

from typing import Any

from media2text.core.config import AppConfig
from media2text.core.runtime.status import build_runtime_status
from media2text.core.runtime.supervisor import MonitorSupervisor
from media2text.core.workspace import open_db

from media2text.api.services.daemon import read_daemon_logs
from media2text.api.services.work_queue import get_work_queue, recover_stale_work


def get_runtime_status(cfg: AppConfig, supervisor: MonitorSupervisor | None) -> dict[str, Any]:
    sup_status = supervisor.status_dict(cfg) if supervisor is not None else None
    conn = open_db(cfg)
    try:
        return build_runtime_status(cfg, supervisor_status=sup_status, conn=conn)
    finally:
        conn.close()


def start_runtime(cfg: AppConfig, supervisor: MonitorSupervisor) -> dict[str, Any]:
    result = supervisor.start(cfg)
    if result.get("ok"):
        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
    return result


def stop_runtime(cfg: AppConfig, supervisor: MonitorSupervisor) -> dict[str, Any]:
    return supervisor.stop(cfg)


def restart_runtime(cfg: AppConfig, supervisor: MonitorSupervisor) -> dict[str, Any]:
    stop_result = supervisor.stop(cfg)
    if not stop_result.get("ok") and stop_result.get("not_owner"):
        return stop_result
    start_result = supervisor.start(cfg)
    return {
        "ok": start_result.get("ok", False),
        "stop": stop_result,
        "start": start_result,
    }


def read_runtime_logs(cfg: AppConfig, *, tail: int = 5) -> dict[str, Any]:
    return read_daemon_logs(cfg, tail=tail)


def read_work_queue(cfg: AppConfig, *, limit: int = 20) -> dict[str, Any]:
    return get_work_queue(cfg, limit=limit)


def recover_runtime_stale_work(
    cfg: AppConfig,
    *,
    older_than_sec: int = 120,
) -> dict[str, Any]:
    return recover_stale_work(cfg, older_than_sec=older_than_sec)


def takeover_runtime(cfg: AppConfig, supervisor: MonitorSupervisor) -> dict[str, Any]:
    result = supervisor.takeover(cfg)
    start = result.get("start") or {}
    if start.get("ok"):
        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
    return result
