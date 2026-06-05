"""Persist creator live poll snapshots for desktop status lights."""

from __future__ import annotations

from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import LiveSnapshotRepo


def upsert_live_snapshot(conn, creator_id: str, live_info: LiveRoomInfo | None) -> bool:
    if live_info is None:
        return False
    return LiveSnapshotRepo(conn).upsert(
        creator_id,
        is_live=bool(live_info.is_live),
        room_id=live_info.room_id,
        title=live_info.title,
    )


def touch_snapshot_probe_failed(conn, creator_id: str, *, error: str) -> bool:
    return LiveSnapshotRepo(conn).touch_probe(creator_id, probe_error=error)
