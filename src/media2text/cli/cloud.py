"""Aliyun Drive cloud backup commands."""

from __future__ import annotations

from pathlib import Path
import shutil
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


def _sidecar_suffixes() -> tuple[str, ...]:
    return (
        ".transcript.json",
        ".transcript.partial.json",
        ".transcript.md",
        ".summary.json",
        ".summary.md",
    )


def _delete_session_sidecars(media_path: Path) -> list[str]:
    """Delete transcript/summary sidecars for a media file. Returns deleted names."""
    stem = media_path.with_suffix("")
    deleted: list[str] = []
    for suffix in _sidecar_suffixes():
        sidecar = Path(f"{stem}{suffix}")
        if sidecar.is_file():
            sidecar.unlink(missing_ok=True)
            deleted.append(sidecar.name)
    return deleted


def _cleanup_local_session(
    cfg: AppConfig,
    conn,
    *,
    session: LiveSessionRow,
    dry_run: bool = False,
) -> dict:
    """Delete local media and sidecar files for an uploaded session.

    Returns a dict with cleanup result metadata.
    """
    ws = cfg.ensure_workspace()
    paths_deleted: list[str] = []
    sidecars_deleted: list[str] = []
    freed_bytes = 0

    for raw in (session.local_path, session.temp_path):
        if not raw:
            continue
        # Resolve relative to workspace or absolute
        p = Path(raw)
        if not p.is_absolute():
            p = ws / p
        if not p.exists():
            continue
        if dry_run:
            paths_deleted.append(str(p))
            continue

        # HLS session dir — delete recursively
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    freed_bytes += f.stat().st_size
            shutil.rmtree(p)
            paths_deleted.append(str(p))
            # Sidecar files are at parent/dirname.transcript.json etc.
            parent = p.parent
            name = p.name
            for suffix in _sidecar_suffixes():
                sidecar = parent / f"{name}{suffix}"
                if sidecar.is_file():
                    sidecar.unlink(missing_ok=True)
                    sidecars_deleted.append(sidecar.name)
            continue

        # Regular media file (flv/mp4/m3u8)
        sidecars_deleted.extend(_delete_session_sidecars(p))
        freed_bytes += p.stat().st_size
        p.unlink(missing_ok=True)
        paths_deleted.append(str(p))

    if not dry_run:
        LiveSessionRepo(conn).clear_local_path(session.id)
        creator = CreatorRepo(conn).get(session.creator_id)
        if creator:
            refresh_manifest(
                conn, sec_uid=creator.sec_uid, workspace=ws
            )

    return {
        "session_id": session.id,
        "creator_id": session.creator_id,
        "dry_run": dry_run,
        "deleted_paths": paths_deleted,
        "sidecars_deleted": sidecars_deleted,
        "freed_bytes": freed_bytes,
    }


@app.command("cleanup")
def cleanup(
    creator_id: str | None = typer.Option(None, "--creator", help="Only this creator"),
    upload_first: bool = typer.Option(
        True,
        "--upload/--no-upload",
        help="Upload un-uploaded sessions before cleaning local files",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be cleaned without deleting",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Clean up local recording files after cloud upload.

    Two passes:
      1. Sessions already uploaded (cloud_upload_status=done) → delete local files.
      2. Sessions with local files but not yet uploaded → upload first, then delete.
    """
    cfg = AppConfig.load()
    ad = cfg.aliyundrive
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    notify = NotifyService(cfg)

    ws = cfg.ensure_workspace()
    all_results: list[dict] = []
    total_freed = 0
    uploaded_count = 0
    cleaned_count = 0
    skipped_count = 0
    failed_count = 0

    # ----- filter clause -----
    clauses = ["status = 'completed'", "local_path IS NOT NULL"]
    params: list[object] = []
    if creator_id:
        clauses.append("creator_id = ?")
        params.append(creator_id)
    sql = "SELECT * FROM live_sessions WHERE " + " AND ".join(clauses) + " ORDER BY started_at DESC"
    rows = conn.execute(sql, params).fetchall()
    candidates = [LiveSessionRow(**dict(r)) for r in rows]

    log.info("cloud_cleanup_scan", total_candidates=len(candidates))

    # ----- Pass 1: already uploaded to cloud (done or partial) → just delete local -----
    done_candidates = [
        s for s in candidates
        if s.cloud_upload_status in ("done", "partial", "uploaded")
    ]
    for session in done_candidates:
        result = _cleanup_local_session(
            cfg, conn, session=session, dry_run=dry_run
        )
        n_files = len(result["deleted_paths"])
        if n_files:
            total_freed += result["freed_bytes"]
            if not dry_run:
                cleaned_count += 1
        else:
            skipped_count += 1
        all_results.append(result)
        if not dry_run:
            creator = creators.get(session.creator_id)
            label = creator.display_name if creator else session.creator_id
            log.info(
                "cloud_cleanup_done",
                session_id=session.id,
                creator=label,
                files=n_files,
                freed_bytes=result["freed_bytes"],
            )

    # ----- Pass 2: not yet uploaded → upload first, then clean -----
    pending = [s for s in candidates if s.cloud_upload_status != "done"]
    if pending and not upload_first:
        log.info("cloud_cleanup_skip_pending", count=len(pending), reason="--no-upload")
    elif pending:
        # Use the same upload logic, with delete_local forced on
        upload_cfg = cfg.model_copy(
            update={
                "aliyundrive": ad.model_copy(
                    update={"delete_local_after_upload": True}
                ),
            }
        )
        for session in pending:
            if not session.local_path:
                skipped_count += 1
                continue
            mp4 = Path(session.local_path)
            if not mp4.exists():
                # File/directory already gone — clear stale DB record
                if not dry_run:
                    LiveSessionRepo(conn).clear_local_path(session.id)
                all_results.append(
                    {
                        "session_id": session.id,
                        "status": "stale_record",
                        "deleted_paths": [],
                        "sidecars_deleted": [],
                        "freed_bytes": 0,
                    }
                )
                skipped_count += 1
                continue
            creator = creators.get(session.creator_id)
            if not creator:
                all_results.append(
                    {
                        "session_id": session.id,
                        "error": "creator_not_found",
                        "deleted_paths": [],
                        "sidecars_deleted": [],
                        "freed_bytes": 0,
                    }
                )
                failed_count += 1
                continue

            if dry_run:
                all_results.append(
                    {
                        "session_id": session.id,
                        "creator_id": creator.id,
                        "dry_run": True,
                        "deleted_paths": [str(mp4)],
                        "sidecars_deleted": [],
                        "freed_bytes": mp4.stat().st_size if mp4.is_file() else 0,
                        "upload_required": True,
                    }
                )
                total_freed += mp4.stat().st_size if mp4.is_file() else 0
                continue

            transcribe_meta = _transcribe_meta_for_backfill(upload_cfg, mp4, session)
            log.info(
                "cloud_cleanup_upload_start",
                session_id=session.id,
                creator=creator.display_name,
                path=str(mp4),
            )
            meta = maybe_upload_live_to_aliyundrive(
                upload_cfg,
                conn,
                session_id=session.id,
                mp4=mp4,
                creator=creator,
                transcribe_meta=transcribe_meta,
                notify=notify,
            )
            if meta.get("upload_completed"):
                uploaded_count += 1
                refresh_manifest(
                    conn, sec_uid=creator.sec_uid, workspace=ws
                )
                # The upload already deleted files if delete_local_after_upload=True;
                # but for safety, also run local cleanup (catches sidecars the upload
                # may have skipped).
                clean_result = _cleanup_local_session(
                    upload_cfg, conn, session=session
                )
                total_freed += clean_result["freed_bytes"]
                all_results.append(clean_result)
            elif meta.get("upload_skipped") or meta.get("upload_failed"):
                skipped_count += 1
                all_results.append(
                    {
                        "session_id": session.id,
                        "deleted_paths": [],
                        "sidecars_deleted": [],
                        "freed_bytes": 0,
                        **meta,
                    }
                )
            if len(pending) > 1:
                time.sleep(2)

    payload = {
        "ok": failed_count == 0,
        "command": "cloud cleanup",
        "total_candidates": len(candidates),
        "cleaned": cleaned_count,
        "uploaded_and_cleaned": uploaded_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "total_freed_bytes": total_freed,
        "total_freed_mb": round(total_freed / (1024 * 1024), 2),
        "results": all_results,
    }
    emit(payload, as_json=json_out)
    log.info("cloud_cleanup_summary", **{k: v for k, v in payload.items() if k != "results"})
    if failed_count:
        raise typer.Exit(4)
