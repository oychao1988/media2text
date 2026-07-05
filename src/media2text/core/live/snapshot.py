"""Persist creator live poll snapshots for desktop status lights."""

from __future__ import annotations

import threading

from media2text.core.config import AppConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.notify import NotifyService
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import LiveSnapshotRepo
from media2text.core.storage.db import with_db_lock_retry
from media2text.core.workspace import open_db

_snapshot_write_lock = threading.Lock()


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


def persist_live_probe_result(
    cfg: AppConfig,
    creator_id: str,
    live_info: LiveRoomInfo | None,
    *,
    error: str | None = None,
) -> bool:
    """Serial short-connection write after probe I/O (DL-1).

    Probe workers fetch live status without holding a DB connection; this function
    opens one connection under a process-wide lock, writes, and closes.
    """
    with _snapshot_write_lock:
        def _persist() -> bool:
            conn = open_db(cfg)
            try:
                state = StateWriter(conn, cfg=cfg, notify=NotifyService(cfg))
                if error is not None:
                    return state.mark_snapshot_probe_failed(creator_id, error=error)
                if live_info is None:
                    return False
                return state.update_snapshot(creator_id, live_info)
            finally:
                conn.close()

        return with_db_lock_retry(_persist)


def clear_snapshot_write_lock_for_tests() -> None:
    """Release test-held lock if a test failed mid-persist (unit tests only)."""
    if _snapshot_write_lock.locked():
        try:
            _snapshot_write_lock.release()
        except RuntimeError:
            pass
