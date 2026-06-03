from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.workspace import open_db

app = typer.Typer(help="Live recording pipeline status and timeline")


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


def _read_daemon_pid(workspace: Path) -> int | None:
    lock = workspace / ".monitor-watch.lock"
    if not lock.is_file():
        return None
    try:
        return int(lock.read_text().strip())
    except (OSError, ValueError):
        return None


@app.command("status")
def status_cmd(
    creator: str | None = typer.Option(None, "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    conn = open_db(cfg)
    sessions = LiveSessionRepo(conn)
    creators = CreatorRepo(conn)
    jobs = PostProcessJobRepo(conn)

    active_rows = sessions.list_active()
    if creator:
        active_rows = [r for r in active_rows if r.creator_id == creator]

    active: list[dict] = []
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
            }
        )

    in_flight = jobs.list_in_flight(limit=50)
    if creator:
        in_flight = [j for j in in_flight if j.creator_id == creator]
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

    payload = {
        "ok": True,
        "command": "live status",
        "daemon_lock_pid": _read_daemon_pid(ws),
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
    }
    emit(payload, as_json=json_out)


@app.command("timeline")
def timeline_cmd(
    session_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    sessions = LiveSessionRepo(conn)
    events = PipelineEventRepo(conn)

    session = sessions.get(session_id)
    if not session:
        emit(
            {
                "ok": False,
                "command": "live timeline",
                "error": "session_not_found",
                "session_id": session_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)

    rows = events.list_for_session(session_id)
    emit(
        {
            "ok": True,
            "command": "live timeline",
            "session_id": session_id,
            "events": [
                {
                    "id": e.id,
                    "stage": e.stage,
                    "status": e.status,
                    "job_id": e.job_id,
                    "started_at": e.started_at,
                    "ended_at": e.ended_at,
                    "duration_ms": e.duration_ms,
                    "detail_json": e.detail_json,
                }
                for e in rows
            ],
        },
        as_json=json_out,
    )


@app.command("stats")
def stats_cmd(
    days: int = typer.Option(7, "--days", min=1, max=365),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    events = PipelineEventRepo(conn)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stage_stats = events.stats_since(since.isoformat())
    emit(
        {
            "ok": True,
            "command": "live stats",
            "days": days,
            "since": since.isoformat(),
            "stages": stage_stats,
        },
        as_json=json_out,
    )
