from __future__ import annotations

from pathlib import Path

import structlog

from media2text.core.archive.hook import index_transcript_safe
from media2text.core.cloud.live_upload import maybe_upload_live_to_aliyundrive
from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo
from media2text.core.transcribe.whisper import write_transcript_outputs

log = structlog.get_logger()


def run_post_process_job(
    cfg: AppConfig,
    conn,
    *,
    job_id: str,
    notify: NotifyService,
) -> dict:
    jobs = PostProcessJobRepo(conn)
    sessions = LiveSessionRepo(conn)
    creators = CreatorRepo(conn)
    job = jobs.get(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}

    if job.status not in ("running", "pending"):
        return {"ok": False, "error": f"invalid_status:{job.status}"}

    if job.status == "pending":
        jobs.mark_running(job_id)

    mp4 = Path(job.mp4_path)
    creator = creators.get(job.creator_id)
    ws = cfg.ensure_workspace()
    result: dict = {"job_id": job_id, "transcribed": False}

    try:
        if cfg.live.transcribe_on_complete and mp4.is_file():
            jobs.update_stage(job_id, stage="transcribe")
            transcribe_meta = _transcribe_mp4(cfg, mp4, creator=creator, notify=notify)
            result.update(transcribe_meta)
            if transcribe_meta.get("transcribed"):
                sessions.update_status(
                    job.session_id, transcribe_status="completed"
                )
            elif transcribe_meta.get("transcribe_error"):
                sessions.update_status(
                    job.session_id, transcribe_status="failed"
                )

        if creator and result.get("transcribed"):
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
            from media2text.core.summarize.hook import maybe_summarize_after_transcribe

            jobs.update_stage(job_id, stage="summarize")
            summarize_meta = maybe_summarize_after_transcribe(
                cfg,
                mp4,
                transcribe_meta=result,
            )
            result.update(summarize_meta)
            if summarize_meta.get("summarized") or summarize_meta.get("summary_path"):
                refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
                label = creator_label(creator)
                notify.emit(
                    NotifyEvent(
                        kind=EventKind.SUMMARIZE_COMPLETED,
                        title=label,
                        body=f"直播摘要完成\n{mp4.name}",
                    )
                )

        if creator:
            jobs.update_stage(job_id, stage="cloud_upload")
            upload_meta = maybe_upload_live_to_aliyundrive(
                cfg,
                conn,
                session_id=job.session_id,
                mp4=mp4,
                creator=creator,
                transcribe_meta=result,
                notify=notify,
            )
            if upload_meta:
                result.update(upload_meta)
                refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)

        jobs.mark_done(job_id)
        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        jobs.mark_failed(job_id, error=str(exc))
        sessions.update_status(job.session_id, transcribe_status="failed")
        log.exception("post_process_job_failed", job_id=job_id)
        return {"ok": False, "error": str(exc), "job_id": job_id}


def _transcribe_mp4(
    cfg: AppConfig,
    mp4: Path,
    *,
    creator,
    notify: NotifyService,
) -> dict:
    from media2text.core.transcribe.errors import TranscribeConfigError
    from media2text.core.transcribe.factory import (
        create_transcribe_backend,
        transcribe_engine_available,
    )

    available, reason = transcribe_engine_available(cfg)
    if not available:
        log.warning(
            "live_transcribe_skipped",
            path=str(mp4),
            reason=reason or "transcribe_unavailable",
        )
        return {"transcribe_skipped": True, "transcribe_skip_reason": reason}

    try:
        backend = create_transcribe_backend(cfg)
    except TranscribeConfigError as exc:
        return {"transcribe_skipped": True, "transcribe_skip_reason": str(exc)}

    try:
        tr = backend.transcribe(mp4, language=cfg.transcribe.language)
        json_path, _md = write_transcript_outputs(mp4, tr)
        index_transcript_safe(cfg, json_path)
        label = creator_label(creator) if creator else mp4.parent.parent.name
        notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_COMPLETED,
                title=label,
                body=f"直播转录完成（{tr.engine}）\n{mp4.name}",
            )
        )
        return {"transcribed": True, "transcribe_engine": tr.engine}
    except Exception as exc:  # noqa: BLE001
        log.exception("live_transcribe_failed", path=str(mp4), error=str(exc))
        return {"transcribe_error": str(exc)}


def drain_pending_jobs(
    cfg: AppConfig,
    conn,
    *,
    notify: NotifyService,
    limit: int = 1,
) -> list[dict]:
    jobs = PostProcessJobRepo(conn)
    stale_sec = cfg.live.post_process_stale_running_sec
    jobs.reset_stale_running(older_than_sec=stale_sec)
    claimed = jobs.claim_pending(limit=limit)
    return [
        run_post_process_job(cfg, conn, job_id=j.id, notify=notify) for j in claimed
    ]
