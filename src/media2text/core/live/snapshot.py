"""Persist creator live poll snapshots for desktop status lights."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.notify import NotifyService
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import LiveSnapshotRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway


def upsert_live_snapshot(
    conn,
    creator_id: str,
    live_info: LiveRoomInfo | None,
    *,
    cfg: AppConfig | None = None,
) -> bool:
    if live_info is None:
        return False
    return LiveSnapshotRepo(conn, cfg=cfg).upsert(
        creator_id,
        is_live=bool(live_info.is_live),
        room_id=live_info.room_id,
        title=live_info.title,
    )


def touch_snapshot_probe_failed(
    conn,
    creator_id: str,
    *,
    error: str,
    cfg: AppConfig | None = None,
) -> bool:
    return LiveSnapshotRepo(conn, cfg=cfg).touch_probe(creator_id, probe_error=error)


def persist_live_probe_result(
    cfg: AppConfig,
    creator_id: str,
    live_info: LiveRoomInfo | None,
    *,
    error: str | None = None,
) -> bool:
    """Serial gateway write after probe I/O (DL-1 / DL-4b)."""

    ensure_write_gateway_started(cfg)
    gw = get_write_gateway(cfg)

    def _persist(conn) -> bool:
        state = StateWriter(conn, cfg=cfg, notify=NotifyService(cfg))
        if error is not None:
            return state.mark_snapshot_probe_failed(creator_id, error=error)
        if live_info is None:
            return False
        return state.update_snapshot(creator_id, live_info)

    return gw.write(_persist, label="live_snapshot.persist_probe")
