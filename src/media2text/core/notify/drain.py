"""Drain notify_events outbox into NotifyService.deliver (sound / Feishu)."""

from __future__ import annotations

import json

import structlog

from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.outbox import NotifyEventRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()


def drain_once(cfg: AppConfig, *, limit: int = 50) -> int:
    conn = open_db(cfg)
    try:
        repo = NotifyEventRepo(conn)
        notify = NotifyService(cfg)
        n = 0
        for row in repo.claim_pending(limit=limit):
            payload = json.loads(row.payload_json)
            notify.deliver(
                NotifyEvent(
                    kind=EventKind(row.kind),
                    title=payload["title"],
                    body=payload["body"],
                    creator_id=row.creator_id,
                    session_id=row.session_id,
                    dedupe_key=row.dedupe_key,
                )
            )
            repo.mark_done(row.id)
            n += 1
        return n
    finally:
        conn.close()
