"""Aliyun Drive cloud backup commands."""

from __future__ import annotations

from pathlib import Path
import time

import typer
import structlog

from media2text.core.cloud.live_upload import maybe_upload_live_to_aliyundrive
from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import NotifyService
from media2text.core.storage.models import LiveSessionRow
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Cloud backup (Aliyun Drive)")
log = structlog.get_logger()


def _transcribe_meta_for_backfill(
    cfg: AppConfig, mp4: Path, session: LiveSessionRow
) -> dict:
    if mp4.with_suffix(".transcript.json").is_file():
        return {"transcribed": True}
    status = session.transcribe_status or "none"
    if status == "done":
        return {"transcribed": True}
    # Backfill: upload mp4 and any existing sidecars; do not block on missing transcript.
    return {"transcribe_skipped": True}


def _list_pending_sessions(
    conn,
    *,
    creator_id: str | None,
    session_id: str | None,
    limit: int,
    include_done: bool = False,
) -> list[LiveSessionRow]:
    repo = LiveSessionRepo(conn)
    if session_id:
        row = repo.get(session_id)
        return [row] if row else []

    clauses = [
        "status = 'completed'",
        "local_path IS NOT NULL",
    ]
    if not include_done:
        clauses.append("(cloud_upload_status IS NULL OR cloud_upload_status NOT IN ('done'))")
    params: list[object] = []
    if creator_id:
        clauses.append("creator_id = ?")
        params.append(creator_id)
    sql = (
        "SELECT * FROM live_sessions WHERE "
        + " AND ".join(clauses)
        + " ORDER BY started_at DESC"
    )
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [LiveSessionRow(**dict(r)) for r in rows]


@app.command("upload")
def upload(
    creator_id: str | None = typer.Option(None, "--creator", help="Only this creator"),
    session_id: str | None = typer.Option(None, "--session", help="Single live session id"),
    limit: int = typer.Option(0, "--limit", help="Max sessions (0 = all pending)"),
    keep_local: bool = typer.Option(
        True,
        "--keep-local/--delete-local",
        help="Keep local files after upload (recommended for backfill)",
    ),
    all_sessions: bool = typer.Option(
        False,
        "--all",
        help="Include sessions already marked uploaded (e.g. after switching cloud account)",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Upload completed live recordings that are not yet backed up to Aliyun Drive."""
    cfg = AppConfig.load()
    ad = cfg.aliyundrive
    if not ad.enabled:
        payload = {
            "ok": False,
            "command": "cloud upload",
            "error": "aliyundrive.enabled is false in config.yaml",
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1)

    if not keep_local:
        cfg = cfg.model_copy(
            update={
                "aliyundrive": ad.model_copy(update={"delete_local_after_upload": True}),
            }
        )
    else:
        cfg = cfg.model_copy(
            update={
                "aliyundrive": ad.model_copy(update={"delete_local_after_upload": False}),
            }
        )

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    notify = NotifyService(cfg)
    pending = _list_pending_sessions(
        conn,
        creator_id=creator_id,
        session_id=session_id,
        limit=limit,
        include_done=all_sessions,
    )

    results: list[dict] = []
    uploaded = 0
    skipped = 0
    failed = 0

    for session in pending:
        if not session.local_path:
            continue
        mp4 = Path(session.local_path)
        if not mp4.is_file():
            results.append(
                {
                    "session_id": session.id,
                    "path": str(mp4),
                    "error": "local_file_missing",
                }
            )
            failed += 1
            continue
        creator = creators.get(session.creator_id)
        if not creator:
            results.append(
                {"session_id": session.id, "error": "creator_not_found"}
            )
            failed += 1
            continue

        transcribe_meta = _transcribe_meta_for_backfill(cfg, mp4, session)
        log.info(
            "cloud_upload_start",
            session_id=session.id,
            creator=creator.display_name,
            path=str(mp4),
        )
        meta = maybe_upload_live_to_aliyundrive(
            cfg,
            conn,
            session_id=session.id,
            mp4=mp4,
            creator=creator,
            transcribe_meta=transcribe_meta,
            notify=notify,
        )
        entry = {
            "session_id": session.id,
            "creator_id": creator.id,
            "display_name": creator.display_name,
            "path": str(mp4),
            **meta,
        }
        results.append(entry)
        log.info("cloud_upload_done", session_id=session.id, **meta)
        if meta.get("upload_completed"):
            uploaded += 1
            refresh_manifest(
                conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace()
            )
        elif meta.get("upload_failed"):
            failed += 1
        elif meta.get("upload_skipped"):
            skipped += 1
        if not session_id and len(pending) > 1:
            time.sleep(2)

    payload = {
        "ok": failed == 0,
        "command": "cloud upload",
        "pending": len(pending),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }
    emit(payload, as_json=json_out)
    if failed:
        raise typer.Exit(4)
