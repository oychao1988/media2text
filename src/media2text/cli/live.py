from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.live.download import download_live_session
from media2text.core.live.status import build_live_status
from media2text.core.live.streaming_benchmark import (
    check_streaming_targets,
    streaming_targets_ms,
)
from media2text.core.storage.repos import LiveSessionRepo, PipelineEventRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Live recording pipeline status and timeline")


@app.command("status")
def status_cmd(
    creator: str | None = typer.Option(None, "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    payload = build_live_status(cfg, conn, creator_id=creator)
    conn.close()
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
    check_targets: bool = typer.Option(
        False,
        "--check-targets",
        help="Compare streaming P95 metrics to targets_ms; exit 1 on violation (requires --json)",
    ),
) -> None:
    if check_targets and not json_out:
        emit(
            {
                "ok": False,
                "command": "live stats",
                "error": "check_targets_requires_json",
            },
            as_json=True,
        )
        raise typer.Exit(1)

    cfg = AppConfig.load()
    conn = open_db(cfg)
    events = PipelineEventRepo(conn)
    sessions = LiveSessionRepo(conn)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.isoformat()
    stage_stats = events.stats_since(since_iso)
    streaming_metrics = events.streaming_metrics_since(since_iso)
    streaming_sessions = sessions.list_streaming_summary_since(since_iso)
    targets_ms = streaming_targets_ms()
    streaming_block: dict = {
        "sessions": streaming_sessions,
        "metrics": streaming_metrics,
        "targets_ms": targets_ms,
    }
    gate: dict | None = None
    if check_targets:
        gate = check_streaming_targets(streaming_metrics, targets_ms)
        streaming_block["target_check"] = gate

    payload: dict = {
        "ok": True,
        "command": "live stats",
        "days": days,
        "since": since_iso,
        "stages": stage_stats,
        "streaming": streaming_block,
    }
    if gate is not None:
        payload["ok"] = bool(gate["passed"])
        if gate["violations"]:
            payload["target_violations"] = gate["violations"]

    emit(payload, as_json=json_out)
    if gate is not None and not gate["passed"]:
        raise typer.Exit(1)


@app.command("download")
def download_cmd(
    session_id: str = typer.Argument(..., help="Live session id"),
    parts: str = typer.Option(
        "all",
        "--parts",
        help="Part indices: all or comma-separated (e.g. 1,2,3)",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge downloaded parts into a single MP4 via ffmpeg concat",
    ),
    keep_local: bool = typer.Option(
        False,
        "--keep-local",
        help="Write parts back into the session parts/ directory (default: temp output dir)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Target directory when not using --keep-local (default: temp dir)",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Download HLS session parts from cloud or local disk; optional merge to MP4."""
    cfg = AppConfig.load()
    conn = open_db(cfg)
    try:
        payload = download_live_session(
            cfg,
            conn,
            session_id=session_id,
            parts=parts,
            keep_local=keep_local,
            merge=merge,
            output_dir=output,
        )
    finally:
        conn.close()
    emit(payload, as_json=json_out)
    if not payload.get("ok"):
        raise typer.Exit(1)
