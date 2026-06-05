"""Runtime health snapshot shared by CLI, desktop API, and MonitorSupervisor."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
    PostProcessJobRepo,
)
from media2text.core.workspace import open_db

HealthState = Literal["stopped", "degraded", "healthy"]
ManagedBy = Literal["embedded", "external", "none"]

HEARTBEAT_NAME = ".runtime-heartbeat"
LOG_NAME = "monitor-watch.log"


def _live_poll_interval_sec(cfg: AppConfig) -> int:
    return cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_heartbeat(workspace: Path) -> dict[str, Any] | None:
    path = workspace / HEARTBEAT_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_heartbeat(workspace: Path, *, last_tick_at: str) -> None:
    path = workspace / HEARTBEAT_NAME
    payload = {"last_tick_at": last_tick_at}
    path.write_text(json.dumps(payload), encoding="utf-8")


def collect_queue_counts(conn) -> dict[str, Any]:
    """Shared queue counters for runtime, live status, and legacy daemon API."""
    jobs = PostProcessJobRepo(conn)
    tasks = MonitorTaskRepo(conn)
    job_counts = jobs.count_by_status()
    task_counts = tasks.count_by_status()
    failed_total = task_counts.get("failed", 0)
    return {
        "post_process": {
            "pending": job_counts.get("pending", 0),
            "running": job_counts.get("running", 0),
            "max_workers": None,
        },
        "monitor_tasks": {
            "pending": task_counts.get("pending", 0),
            "running": task_counts.get("running", 0),
            "failed_total": failed_total,
            "failed_recent_24h": tasks.count_failed_recent_24h(),
            "dlq": failed_total,
        },
    }


def collect_active_recordings(
    conn,
    *,
    creator_id: str | None = None,
) -> dict[str, Any]:
    sessions = LiveSessionRepo(conn)
    creators = CreatorRepo(conn)
    active_rows = sessions.list_active()
    if creator_id:
        active_rows = [r for r in active_rows if r.creator_id == creator_id]
    items: list[dict[str, Any]] = []
    for row in active_rows:
        creator = creators.get(row.creator_id)
        items.append(
            {
                "session_id": row.id,
                "creator_id": row.creator_id,
                "display_name": creator.display_name if creator else None,
                "started_at": row.started_at,
                "recording_age_sec": round(_age_sec(row.started_at) or 0, 1),
                "offline_since_at": row.offline_since_at,
                "ffmpeg_pid": row.ffmpeg_pid,
                "status": row.status,
                "pipeline_mode": row.pipeline_mode,
                "transcribe_status": row.transcribe_status,
            }
        )
    return {"active_count": len(items), "items": items}


def _stale_snapshot_threshold_sec(cfg: AppConfig) -> int:
    return 2 * _live_poll_interval_sec(cfg)


def list_stale_snapshot_creators(conn, cfg: AppConfig) -> list[dict[str, Any]]:
    """Monitored creators whose live snapshot is missing or older than 2× live poll."""
    stale_sec = _stale_snapshot_threshold_sec(cfg)
    now = datetime.now(timezone.utc)
    monitored = CreatorRepo(conn).list_monitored()
    snapshots = LiveSnapshotRepo(conn)
    items: list[dict[str, Any]] = []
    for creator in monitored:
        snap = snapshots.get(creator.id)
        checked_at: str | None = None
        stale = False
        if snap is None:
            stale = True
        else:
            checked_at = snap.checked_at
            checked = _parse_iso(checked_at)
            if checked is None:
                stale = True
            elif (now - checked).total_seconds() > stale_sec:
                stale = True
        if not stale:
            continue
        age_sec = round(_age_sec(checked_at) or 0, 1) if checked_at else None
        items.append(
            {
                "creator_id": creator.id,
                "display_name": creator.display_name or creator.sec_uid,
                "checked_at": checked_at,
                "stale_sec": age_sec,
            }
        )
    return items


def count_stale_snapshots(conn, cfg: AppConfig) -> int:
    return len(list_stale_snapshot_creators(conn, cfg))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_sec(since: str | None) -> float | None:
    start = _parse_iso(since)
    if not start:
        return None
    return (datetime.now(timezone.utc) - start).total_seconds()


def read_daemon_pid(workspace: Path) -> int | None:
    lock = workspace / ".monitor-watch.lock"
    if not lock.is_file():
        return None
    try:
        return int(lock.read_text().strip())
    except (OSError, ValueError):
        return None


def compute_health(
    *,
    running: bool,
    tick_age_sec: float | None,
    live_poll_sec: int,
    snapshots_stale: int,
    failed_recent_24h: int,
    threshold_failed: int = 10,
) -> tuple[HealthState, list[str]]:
    if not running:
        return "stopped", ["monitor not running"]
    reasons: list[str] = []
    if tick_age_sec is None or tick_age_sec > 2 * live_poll_sec:
        reasons.append("live tick stale")
    if snapshots_stale > 0:
        reasons.append(f"{snapshots_stale} creator snapshots stale")
    if failed_recent_24h > threshold_failed:
        reasons.append(f"{failed_recent_24h} monitor task failures in 24h")
    return ("degraded", reasons) if reasons else ("healthy", [])


def build_runtime_status(
    cfg: AppConfig,
    *,
    supervisor_status: dict[str, Any] | None = None,
    conn=None,
) -> dict[str, Any]:
    ws = cfg.ensure_workspace()
    own_conn = conn is None
    if own_conn:
        conn = open_db(cfg)
    try:
        queues = collect_queue_counts(conn)
        queues["post_process"]["max_workers"] = resolve_post_process_workers(cfg)
        recordings = collect_active_recordings(conn)
        snapshots_stale = count_stale_snapshots(conn, cfg)
        monitored_creators = len(CreatorRepo(conn).list_monitored())

        sup = supervisor_status or {}
        managed_by: ManagedBy = sup.get("managed_by", "none")
        lock_pid = read_daemon_pid(ws)
        running = bool(sup.get("running") or (lock_pid and _pid_alive(lock_pid)))
        if managed_by == "embedded" and sup.get("thread_alive"):
            running = True
        elif managed_by == "external" and lock_pid and _pid_alive(lock_pid):
            running = True
        elif managed_by == "none" and lock_pid and _pid_alive(lock_pid):
            managed_by = "external"
            running = True

        last_tick_at = sup.get("last_tick_at")
        if last_tick_at is None and managed_by == "external":
            heartbeat = read_heartbeat(ws)
            if heartbeat:
                last_tick_at = heartbeat.get("last_tick_at")

        tick_age_sec = _age_sec(last_tick_at) if last_tick_at else None
        live_poll_sec = _live_poll_interval_sec(cfg)
        failed_recent = queues["monitor_tasks"]["failed_recent_24h"]
        health, health_reasons = compute_health(
            running=running,
            tick_age_sec=tick_age_sec,
            live_poll_sec=live_poll_sec,
            snapshots_stale=snapshots_stale,
            failed_recent_24h=failed_recent,
            threshold_failed=cfg.desktop.runtime_failed_recent_threshold,
        )

        pid = sup.get("pid") if managed_by == "embedded" else lock_pid
        if managed_by == "embedded" and pid is None:
            pid = os.getpid()

        return {
            "ok": True,
            "health": health,
            "health_reasons": health_reasons,
            "managed_by": managed_by,
            "daemon": {
                "running": running,
                "pid": pid if running else None,
                "lock_pid": lock_pid,
                "started_at": sup.get("started_at"),
                "last_tick_at": last_tick_at,
                "tick_age_sec": round(tick_age_sec, 1) if tick_age_sec is not None else None,
                "live_poll_interval_sec": live_poll_sec,
            },
            "recordings": recordings,
            "queues": queues,
            "observability": {
                "snapshots_stale_count": snapshots_stale,
                "monitored_creators": monitored_creators,
            },
            "log_path": str(ws / LOG_NAME),
        }
    finally:
        if own_conn:
            conn.close()


def build_daemon_status_legacy(cfg: AppConfig, conn) -> dict[str, Any]:
    """Backward-compatible subset for deprecated ``GET /api/daemon``."""
    runtime = build_runtime_status(cfg, conn=conn)
    queues = runtime["queues"]
    return {
        "running": runtime["daemon"]["running"],
        "pid": runtime["daemon"]["pid"],
        "lock_pid": runtime["daemon"]["lock_pid"],
        "live_tick_interval_sec": runtime["daemon"]["live_poll_interval_sec"],
        "post_process": {
            "max_workers": queues["post_process"]["max_workers"],
            "pending": queues["post_process"]["pending"],
            "running": queues["post_process"]["running"],
        },
        "monitor_tasks": {
            "pending": queues["monitor_tasks"]["pending"],
            "running": queues["monitor_tasks"]["running"],
            "failed": queues["monitor_tasks"]["failed_total"],
            "dlq": queues["monitor_tasks"]["dlq"],
        },
        "active_recordings": runtime["recordings"]["active_count"],
        "log_path": runtime["log_path"],
        "deprecated": True,
    }
