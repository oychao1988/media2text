"""Monitor task retry HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig
from media2text.core.storage.repos import MonitorTaskRepo
from media2text.core.workspace import open_db

router = APIRouter(prefix="/monitor-tasks", tags=["monitor-tasks"])


@router.post("/retry/{task_id}")
def post_monitor_task_retry(
    task_id: str,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    conn = open_db(cfg)
    try:
        repo = MonitorTaskRepo(conn)
        task = repo.get(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": "task_not_found", "task_id": task_id},
            )
        if task.status != "failed":
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "error": "invalid_status",
                    "task_id": task_id,
                    "status": task.status,
                },
            )
        if not repo.retry_failed(task_id):
            raise HTTPException(
                status_code=409,
                detail={"ok": False, "error": "retry_failed", "task_id": task_id},
            )
        return {
            "ok": True,
            "task_id": task_id,
            "previous_status": "failed",
            "new_status": "pending",
        }
    finally:
        conn.close()
