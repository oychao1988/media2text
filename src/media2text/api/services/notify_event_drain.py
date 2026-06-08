"""Drain notify_events outbox into NotifyService (sound / Feishu)."""

from __future__ import annotations

import asyncio
import json

import structlog

from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.outbox import NotifyEventRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()

_DRAIN_INTERVAL_SEC = 1.5


def drain_once(cfg: AppConfig) -> int:
    conn = open_db(cfg)
    try:
        repo = NotifyEventRepo(conn)
        notify = NotifyService(cfg)
        n = 0
        for row in repo.claim_pending(limit=50):
            payload = json.loads(row.payload_json)
            notify.emit(
                NotifyEvent(
                    kind=EventKind(row.kind),
                    title=payload["title"],
                    body=payload["body"],
                )
            )
            repo.mark_done(row.id)
            n += 1
        return n
    finally:
        conn.close()


async def run_notify_drain_loop(cfg: AppConfig, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            drain_once(cfg)
        except Exception:
            log.exception("notify_event_drain_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DRAIN_INTERVAL_SEC)
        except TimeoutError:
            pass
