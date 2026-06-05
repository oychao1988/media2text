"""Post-process queue HTTP API for desktop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig
from media2text.core.live.post_process import drain_pending_jobs
from media2text.core.notify import NotifyService
from media2text.core.storage.repos import PostProcessJobRepo
from media2text.core.workspace import open_db

router = APIRouter(prefix="/post-process", tags=["post-process"])


class PostProcessRunBody(BaseModel):
    limit: int = Field(10, ge=1, le=100)


@router.post("/run")
def post_post_process_run(
    body: PostProcessRunBody,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    conn = open_db(cfg)
    try:
        notify = NotifyService(cfg)
        results = drain_pending_jobs(cfg, conn, notify=notify, limit=body.limit)
        return {
            "ok": True,
            "command": "post-process run",
            "processed": len(results),
            "results": results,
        }
    finally:
        conn.close()


@router.post("/retry/{job_id}")
def post_post_process_retry(
    job_id: str,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    conn = open_db(cfg)
    try:
        repo = PostProcessJobRepo(conn)
        job = repo.get(job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "command": "post-process retry",
                    "error": "job_not_found",
                    "job_id": job_id,
                },
            )
        if job.status != "failed":
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "command": "post-process retry",
                    "error": "invalid_status",
                    "job_id": job_id,
                    "status": job.status,
                },
            )
        if not repo.retry_failed(job_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "command": "post-process retry",
                    "error": "retry_failed",
                    "job_id": job_id,
                },
            )
        return {
            "ok": True,
            "command": "post-process retry",
            "job_id": job_id,
            "previous_status": "failed",
            "new_status": "pending",
        }
    finally:
        conn.close()
