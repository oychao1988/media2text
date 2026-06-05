"""Enqueue monitor tasks from desktop API (download, etc.)."""

from __future__ import annotations

import json
from typing import Any

from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo


def enqueue_creator_download(
    conn,
    *,
    creator_id: str,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    task_id = MonitorTaskRepo(conn).enqueue(
        creator_id=creator_id,
        task_type="download",
        dedupe_key=f"download:{creator_id}",
        priority=10,
        payload_json=json.dumps({"platform": creator.platform}),
    )
    return {
        "ok": True,
        "creator_id": creator_id,
        "task_id": task_id,
        "queued": task_id is not None,
    }
