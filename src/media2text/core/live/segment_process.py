"""Tier-1 segment upload worker: upload part, refresh m3u8, delete local."""

from __future__ import annotations

from pathlib import Path

import structlog

from media2text.core.cloud.live_upload import upload_live_part
from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.notify import NotifyService
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo

log = structlog.get_logger()


def run_segment_process_job(
    cfg: AppConfig,
    conn,
    *,
    job_id: str,
    notify: NotifyService,
) -> dict:
    jobs = SegmentProcessJobRepo(conn)
    job = jobs.get(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}

    if job.status not in ("running", "pending"):
        return {"ok": False, "error": f"invalid_status:{job.status}"}

    if job.status == "pending":
        jobs.mark_running(job_id)

    session = LiveSessionRepo(conn).get(job.session_id)
    if not session or not session.session_dir:
        jobs.mark_failed(job_id, error="missing_session_dir")
        return {"ok": False, "error": "missing_session_dir"}

    creator = CreatorRepo(conn).get(session.creator_id)
    if not creator:
        jobs.mark_failed(job_id, error="creator_not_found")
        return {"ok": False, "error": "creator_not_found"}

    parts_repo = SegmentManifestRepo(conn)
    part = parts_repo.get_part(job.session_id, job.part_index)
    if not part:
        jobs.mark_failed(job_id, error="part_not_found")
        return {"ok": False, "error": "part_not_found"}

    session_dir = Path(session.session_dir)
    part_path = session_dir / part.rel_path
    if not part_path.is_file():
        jobs.mark_failed(job_id, error="part_file_missing")
        return {"ok": False, "error": "part_file_missing"}
    if part_path.stat().st_size == 0:
        jobs.mark_failed(job_id, error="part_file_empty")
        return {"ok": False, "error": "part_file_empty"}

    upload_cfg = cfg.live.segment_pipeline.upload
    if not upload_cfg.enabled or not cfg.aliyundrive.enabled:
        jobs.mark_done(job_id)
        return {"ok": True, "skipped": True, "reason": "upload_disabled"}

    try:
        result = upload_live_part(
            cfg,
            conn,
            session_id=job.session_id,
            session_dir=session_dir,
            part_index=job.part_index,
            part_path=part_path,
            creator=creator,
            notify=notify,
        )
        if not result.get("ok"):
            jobs.mark_failed(job_id, error=result.get("error", "upload_failed"))
            return {"ok": False, **result}

        cloud_path = result.get("cloud_path", "")
        parts_repo.mark_uploaded(
            job.session_id,
            job.part_index,
            cloud_path=cloud_path,
        )

        # delete_local_after_upload removes only the closed .m4s part — not init.mp4,
        # master.m3u8, session.manifest.json, or transcript/summary sidecars.
        if upload_cfg.delete_local_after_upload:
            part_path.unlink(missing_ok=True)
            parts_repo.mark_local_deleted(job.session_id, job.part_index)

        jobs.mark_done(job_id)
        log.info(
            "segment_process_done",
            session_id=job.session_id,
            part_index=job.part_index,
            cloud_path=cloud_path,
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        jobs.mark_failed(job_id, error=str(exc))
        log.exception(
            "segment_process_failed",
            job_id=job_id,
            session_id=job.session_id,
            part_index=job.part_index,
        )
        return {"ok": False, "error": str(exc)}
