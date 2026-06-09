"""Runtime work-queue detail for Desktop daemon panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.runtime.status import _age_sec, list_stale_snapshot_creators
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo, PostProcessJobRepo
from media2text.core.workspace import open_db

TASK_TYPE_LABELS: dict[str, str] = {
    "sync_catalog": "同步作品列表",
    "download": "下载作品",
    "sync_dynamic": "同步动态",
    "finalize": "直播收尾",
    "pipeline_run": "作品流水线",
}


def _basename(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).name


def get_work_queue(cfg: AppConfig, *, limit: int = 20) -> dict[str, Any]:
    conn = open_db(cfg)
    try:
        creators = CreatorRepo(conn)
        name_map = {
            row.id: (row.display_name or row.sec_uid)
            for row in creators.list_all()
        }
        monitor_tasks = []
        for task in MonitorTaskRepo(conn).list_in_flight(limit=limit):
            monitor_tasks.append(
                {
                    "id": task.id,
                    "task_type": task.task_type,
                    "task_label": TASK_TYPE_LABELS.get(task.task_type, task.task_type),
                    "creator_id": task.creator_id,
                    "creator_name": name_map.get(task.creator_id, task.creator_id[:8]),
                    "status": task.status,
                    "started_at": task.started_at,
                    "running_sec": round(_age_sec(task.started_at) or 0, 1)
                    if task.status == "running"
                    else None,
                    "error": task.error,
                }
            )
        post_process = []
        for job in PostProcessJobRepo(conn).list_in_flight(limit=limit):
            post_process.append(
                {
                    "id": job.id,
                    "session_id": job.session_id,
                    "creator_id": job.creator_id,
                    "creator_name": name_map.get(job.creator_id, job.creator_id[:8]),
                    "status": job.status,
                    "stage": job.stage,
                    "media_name": _basename(job.mp4_path),
                    "running_sec": round(_age_sec(job.updated_at) or 0, 1)
                    if job.status == "running"
                    else None,
                    "error": job.error,
                }
            )
        stale_creators = list_stale_snapshot_creators(conn, cfg)
        return {
            "ok": True,
            "monitor_tasks": monitor_tasks,
            "post_process": post_process,
            "stale_creators": stale_creators,
        }
    finally:
        conn.close()


def recover_stale_work(
    cfg: AppConfig,
    *,
    older_than_sec: int = 120,
) -> dict[str, Any]:
    """Reset monitor tasks / post-process jobs stuck in ``running``."""
    conn = open_db(cfg)
    try:
        mt_repo = MonitorTaskRepo(conn)
        mt_reset = mt_repo.reset_stale_running(older_than_sec=older_than_sec)
        content_released = 0
        if LiveSessionRepo(conn).list_active():
            content_released = mt_repo.release_running_content_tasks()
        pp_reset = PostProcessJobRepo(conn).reset_stale_running(older_than_sec=older_than_sec)
        return {
            "ok": True,
            "monitor_tasks_reset": mt_reset,
            "content_tasks_released": content_released,
            "post_process_reset": pp_reset,
            "older_than_sec": older_than_sec,
        }
    finally:
        conn.close()
