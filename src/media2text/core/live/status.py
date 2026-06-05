"""Shared live pipeline status payload (CLI + desktop API)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo, PostProcessJobRepo


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


def build_live_status(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str | None = None,
    command: str = "live status",
) -> dict[str, Any]:
    ws = cfg.ensure_workspace()
    sessions = LiveSessionRepo(conn)
    creators = CreatorRepo(conn)
    jobs = PostProcessJobRepo(conn)
    tasks = MonitorTaskRepo(conn)

    active_rows = sessions.list_active()
    if creator_id:
        active_rows = [r for r in active_rows if r.creator_id == creator_id]

    active: list[dict[str, Any]] = []
    for row in active_rows:
        c = creators.get(row.creator_id)
        active.append(
            {
                "session_id": row.id,
                "creator_id": row.creator_id,
                "display_name": c.display_name if c else None,
                "started_at": row.started_at,
                "recording_age_sec": round(_age_sec(row.started_at) or 0, 1),
                "offline_since_at": row.offline_since_at,
                "ffmpeg_pid": row.ffmpeg_pid,
                "status": row.status,
                "pipeline_mode": row.pipeline_mode,
                "transcribe_status": row.transcribe_status,
            }
        )

    in_flight = jobs.list_in_flight(limit=50)
    if creator_id:
        in_flight = [j for j in in_flight if j.creator_id == creator_id]
    counts = jobs.count_by_status()
    job_items = []
    for j in in_flight:
        job_items.append(
            {
                "job_id": j.id,
                "session_id": j.session_id,
                "creator_id": j.creator_id,
                "stage": j.stage,
                "status": j.status,
                "queued_sec": round(_age_sec(j.created_at) or 0, 1),
            }
        )

    task_counts = tasks.count_by_status()

    return {
        "ok": True,
        "command": command,
        "daemon_lock_pid": read_daemon_pid(ws),
        "live_tick": {
            "interval_sec": cfg.live.live_poll_interval_sec,
        },
        "active_recordings": active,
        "post_process": {
            "max_workers": resolve_post_process_workers(cfg),
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "jobs": job_items,
        },
        "monitor_tasks": {
            "pending": task_counts.get("pending", 0),
            "running": task_counts.get("running", 0),
            "failed": task_counts.get("failed", 0),
            "dlq": task_counts.get("failed", 0),
        },
    }
