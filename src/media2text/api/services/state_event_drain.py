"""Drain desktop_events outbox into the in-process events hub."""

from __future__ import annotations

import asyncio

import structlog

from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services.events_hub import events_hub
from media2text.core.config import AppConfig
from media2text.core.storage.repos import DesktopEventRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()

_DRAIN_INTERVAL_SEC = 1.5


def drain_once(cfg: AppConfig) -> int:
    conn = open_db(cfg)
    try:
        repo = DesktopEventRepo(conn)
        n = 0
        for row in repo.claim_pending(limit=50):
            events_hub.publish(
                event_payload(EventType.CREATOR_UPDATED, creator_id=row.creator_id)
            )
            repo.mark_delivered(row.id)
            n += 1
        return n
    finally:
        conn.close()


async def run_drain_loop(cfg: AppConfig, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            drain_once(cfg)
        except Exception:
            log.exception("desktop_event_drain_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DRAIN_INTERVAL_SEC)
        except TimeoutError:
            pass
