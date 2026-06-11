from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import structlog

from media2text.core.archive.hook import index_transcript_safe
from media2text.core.cloud.live_upload import (
    is_hls_session_media,
    maybe_upload_live_to_aliyundrive,
    upload_summary_sidecars_if_needed,
)
from media2text.core.config import AppConfig
from media2text.core.live.pipeline_events import stage_event
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)
from media2text.core.transcribe.whisper import write_transcript_outputs
from media2text.core.workspace import open_db

log = structlog.get_logger()

_LIVE_PIPELINE_DEPRECATED_HINT = "use streaming+hls; see config.example.yaml"


def _transcript_exists(media: Path) -> bool:
    return media.with_suffix(".transcript.json").is_file()


def _streaming_rest_fallback_reason(conn, session_id: str) -> str | None:
    """Why post_process should REST-transcribe when live.transcribe_on_complete is false."""
    session = LiveSessionRepo(conn).get(session_id)
    if not session:
        return None
    if (session.pipeline_mode or "").strip().lower() == "streaming":
        if session.transcribe_status == "failed":
            return "finalize_failed"
        return "streaming_missing_sidecar"
    for ev in PipelineEventRepo(conn).list_for_session(session_id):
        if ev.stage == "streaming_stt" and ev.status == "degraded":
            return "degraded"
    return None


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

    media = Path(job.mp4_path)
    creator = creators.get(job.creator_id)
    ws = cfg.ensure_workspace()
    result: dict = {"job_id": job_id, "transcribed": False}

    try:
        if _transcript_exists(media):
            result["transcribed"] = True
            result["transcribe_engine"] = "streaming"
            sessions.update_status(job.session_id, transcribe_status="completed")
        else:
            fallback_reason = _streaming_rest_fallback_reason(conn, job.session_id)
            should_rest = media.is_file() and (
                cfg.live.transcribe_on_complete or fallback_reason is not None
            )
            if should_rest:
                jobs.update_stage(job_id, stage="transcribe")
                stage_detail = (
                    {"fallback_rest": True, "reason": fallback_reason}
                    if fallback_reason
                    else None
                )
                with stage_event(
                    conn,
                    session_id=job.session_id,
                    stage="transcribe",
                    job_id=job_id,
                    detail=stage_detail,
                ):
                    transcribe_meta = _transcribe_media(
                        cfg, media, creator=creator, notify=notify
                    )
                result.update(transcribe_meta)
                if transcribe_meta.get("transcribed"):
                    sessions.update_status(
                        job.session_id, transcribe_status="completed"
                    )
                elif transcribe_meta.get("transcribe_error"):
                    sessions.update_status(
                        job.session_id, transcribe_status="failed"
                    )

        has_transcript = result.get("transcribed") or _transcript_exists(media)
        summarize_meta: dict = {}
        upload_meta: dict = {}

        def _run_summarize() -> dict:
            if not creator or not has_transcript or not cfg.summarize.enabled:
                return {}
            if not cfg.summarize.on_transcribe_complete:
                return {}
            from media2text.core.summarize.hook import maybe_summarize_after_transcribe

            wconn = open_db(cfg)
            try:
                PostProcessJobRepo(wconn).update_stage(job_id, stage="summarize")
                with stage_event(
                    wconn, session_id=job.session_id, stage="summarize", job_id=job_id
                ):
                    meta = maybe_summarize_after_transcribe(
                        cfg,
                        media,
                        transcribe_meta=result,
                    )
                if meta.get("summarized") or meta.get("summary_path"):
                    refresh_manifest(wconn, sec_uid=creator.sec_uid, workspace=ws)
                    from media2text.agent.creator_distill.deferred import maybe_promote_bootstrap
                    from media2text.agent.creator_distill.enqueue import maybe_enqueue_evolve

                    maybe_promote_bootstrap(cfg, wconn, creator_id=creator.id)
                    evolve_job = maybe_enqueue_evolve(
                        cfg,
                        wconn,
                        creator_id=creator.id,
                        source_id=job.session_id,
                        trigger="summarize_completed",
                    )
                    if evolve_job:
                        from media2text.agent.creator_distill.pool import (
                            CreatorAgentJobPool,
                            resolve_distill_workers,
                        )

                        pool = CreatorAgentJobPool(max_workers=resolve_distill_workers(cfg))
                        try:
                            pool.submit_evolve(cfg, job_id=evolve_job)
                        finally:
                            pool.shutdown(wait=False)
                    label = creator_label(creator)
                    notify.emit(
                        NotifyEvent(
                            kind=EventKind.SUMMARIZE_COMPLETED,
                            title=label,
                            body=f"直播摘要完成\n{media.name}",
                        )
                    )
                return meta
            finally:
                wconn.close()

        def _run_upload() -> dict:
            if not creator:
                return {}
            wconn = open_db(cfg)
            try:
                session = LiveSessionRepo(wconn).get(job.session_id)
                if session and (session.pipeline_mode or "").strip().lower() == "legacy":
                    log.warning(
                        "live_pipeline_deprecated",
                        mode="legacy",
                        hint=_LIVE_PIPELINE_DEPRECATED_HINT,
                    )
                PostProcessJobRepo(wconn).update_stage(job_id, stage="cloud_upload")
                with stage_event(
                    wconn, session_id=job.session_id, stage="cloud_upload", job_id=job_id
                ):
                    meta = maybe_upload_live_to_aliyundrive(
                        cfg,
                        wconn,
                        session_id=job.session_id,
                        mp4=media,
                        creator=creator,
                        transcribe_meta=result,
                        notify=notify,
                    )
                if meta:
                    refresh_manifest(wconn, sec_uid=creator.sec_uid, workspace=ws)
                return meta or {}
            finally:
                wconn.close()

        hls_session = is_hls_session_media(media)
        if hls_session and cfg.aliyundrive.enabled:
            log.warning(
                "live_pipeline_deprecated",
                mode="hls_whole_file_upload",
                hint=_LIVE_PIPELINE_DEPRECATED_HINT,
            )
        if creator and (has_transcript or (cfg.aliyundrive.enabled and not hls_session)):
            futures = {}
            with ThreadPoolExecutor(max_workers=2) as pool:
                if has_transcript and cfg.summarize.enabled and cfg.summarize.on_transcribe_complete:
                    futures[pool.submit(_run_summarize)] = "summarize"
                if cfg.aliyundrive.enabled and not hls_session:
                    futures[pool.submit(_run_upload)] = "upload"
                for fut in as_completed(futures):
                    key = futures[fut]
                    try:
                        meta = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        log.exception(
                            "post_process_parallel_failed",
                            job_id=job_id,
                            branch=key,
                            error=str(exc),
                        )
                        if key == "summarize":
                            summarize_meta = {"summarize_error": str(exc)}
                        else:
                            upload_meta = {"upload_error": str(exc)}
                        continue
                    if key == "summarize":
                        summarize_meta = meta
                    else:
                        upload_meta = meta

            result.update(summarize_meta)
            result.update(upload_meta)

            if summarize_meta and upload_meta.get("upload_completed"):
                supplemental = upload_summary_sidecars_if_needed(
                    cfg,
                    conn,
                    session_id=job.session_id,
                    media=media,
                    creator=creator,
                    notify=notify,
                )
                if supplemental:
                    result.update(supplemental)
                    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)

        jobs.mark_done(job_id)
        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        jobs.mark_failed(job_id, error=str(exc))
        sessions.update_status(job.session_id, transcribe_status="failed")
        log.exception("post_process_job_failed", job_id=job_id)
        return {"ok": False, "error": str(exc), "job_id": job_id}


def _transcribe_media(
    cfg: AppConfig,
    media: Path,
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
            path=str(media),
            reason=reason or "transcribe_unavailable",
        )
        return {"transcribe_skipped": True, "transcribe_skip_reason": reason}

    try:
        backend = create_transcribe_backend(cfg)
    except TranscribeConfigError as exc:
        return {"transcribe_skipped": True, "transcribe_skip_reason": str(exc)}

    try:
        tr = backend.transcribe(media, language=cfg.transcribe.language)
        json_path, _md = write_transcript_outputs(media, tr)
        index_transcript_safe(cfg, json_path)
        label = creator_label(creator) if creator else media.parent.parent.name
        notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_COMPLETED,
                title=label,
                body=f"直播转录完成（{tr.engine}）\n{media.name}",
            )
        )
        return {"transcribed": True, "transcribe_engine": tr.engine}
    except Exception as exc:  # noqa: BLE001
        log.exception("live_transcribe_failed", path=str(media), error=str(exc))
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
