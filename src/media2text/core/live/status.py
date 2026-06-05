"""Shared live pipeline status payload (CLI + desktop API)."""

from __future__ import annotations

from typing import Any

from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import resolve_post_process_workers
from media2text.core.runtime.status import (
    _age_sec,
    collect_active_recordings,
    collect_queue_counts,
    read_daemon_pid,
)
from media2text.core.storage.repos import PostProcessJobRepo


def build_live_status(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str | None = None,
    command: str = "live status",
) -> dict[str, Any]:
    ws = cfg.ensure_workspace()
    jobs = PostProcessJobRepo(conn)
    recordings = collect_active_recordings(conn, creator_id=creator_id)
    active = recordings["items"]
    queues = collect_queue_counts(conn)
    queues["post_process"]["max_workers"] = resolve_post_process_workers(cfg)

    in_flight = jobs.list_in_flight(limit=50)
    if creator_id:
        in_flight = [j for j in in_flight if j.creator_id == creator_id]
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

    return {
        "ok": True,
        "command": command,
        "daemon_lock_pid": read_daemon_pid(ws),
        "live_tick": {
            "interval_sec": cfg.live.live_poll_interval_sec,
        },
        "active_recordings": active,
        "post_process": {
            **queues["post_process"],
            "jobs": job_items,
        },
        "monitor_tasks": {
            "pending": queues["monitor_tasks"]["pending"],
            "running": queues["monitor_tasks"]["running"],
            "failed": queues["monitor_tasks"]["failed_total"],
            "dlq": queues["monitor_tasks"]["dlq"],
        },
    }
