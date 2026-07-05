"""Live observe poll/finalize via gateway + session registry (MH-4b)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from media2text.core.config import AppConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.storage.repos import LiveSessionRepo
from media2text.core.storage.write_gateway import DbWriteGateway

if TYPE_CHECKING:
    from media2text.core.live.session_state import SessionStateMachineRegistry


class LiveObserveService:
    """Short-connection live poll and stale cleanup (no watcher._conn)."""

    @staticmethod
    def poll_active_recordings(
        cfg: AppConfig,
        *,
        registry: SessionStateMachineRegistry,
        gateway: DbWriteGateway,
    ) -> dict[str, int]:
        registry.poll_active_for_platform("douyin")
        registry.poll_active_for_platform("bilibili")

        def _count(conn) -> int:
            return len(LiveSessionRepo(conn).list_active())

        active = gateway.read(_count)
        return {"active": active}

    @staticmethod
    def run_finalize(cfg: AppConfig, *, gateway: DbWriteGateway) -> dict[str, int]:
        def _finalize(conn) -> dict[str, int]:
            stale = StateWriter(conn, cfg=cfg).mark_stale_recordings_failed()
            active = len(LiveSessionRepo(conn, cfg=cfg).list_active())
            return {"stale_cleared": stale, "active": active}

        return gateway.write(_finalize, label="live_observe.finalize")
