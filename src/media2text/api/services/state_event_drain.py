"""Drain desktop_events outbox into the in-process events hub."""

from __future__ import annotations

import asyncio

import structlog

from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services.events_hub import events_hub
from media2text.api.services.drain_interval import resolve_drain_interval_sec
from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor
from media2text.core.storage.repos import DesktopEventRepo
from media2text.core.storage.write_gateway import gateway_write

log = structlog.get_logger()


def drain_once(cfg: AppConfig) -> int:
    def _run(conn) -> int:
        repo = DesktopEventRepo(conn, cfg=cfg)
        n = 0
        for row in repo.claim_pending(limit=50):
            events_hub.publish(
                event_payload(EventType.CREATOR_UPDATED, creator_id=row.creator_id)
            )
            repo.mark_delivered(row.id)
            n += 1
        return n

    return gateway_write(cfg, _run, label="desktop_event.drain")


async def run_drain_loop(
    cfg: AppConfig,
    stop: asyncio.Event,
    *,
    supervisor: MonitorSupervisor | None = None,
) -> None:
    while not stop.is_set():
        try:
            drain_once(cfg)
        except Exception:
            log.exception("desktop_event_drain_failed")
        interval = resolve_drain_interval_sec(cfg, supervisor=supervisor)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
