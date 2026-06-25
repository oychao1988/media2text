"""Live recording lane priority helpers."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
)


def live_lane_priority_count(conn, cfg: AppConfig) -> int:
    """Count live-lane signals that should defer post_process drain."""
    del cfg
    count = 0
    tasks = MonitorTaskRepo(conn)
    for row in tasks.list_in_flight(limit=50):
        if row.task_type == "prepare_live_recording" and row.status in (
            "pending",
            "running",
        ):
            count += 1

    creators = CreatorRepo(conn)
    snapshots = LiveSnapshotRepo(conn)
    sessions = LiveSessionRepo(conn)
    for creator in creators.list_monitored():
        snap = snapshots.get(creator.id)
        if not snap or not snap.is_live:
            continue
        if sessions.get_active_for_creator(creator.id) is None:
            count += 1
    return count


def live_lane_needs_priority(conn, cfg: AppConfig) -> bool:
    """True when live detection/prepare work should defer post_process drain."""
    return live_lane_priority_count(conn, cfg) > 0
