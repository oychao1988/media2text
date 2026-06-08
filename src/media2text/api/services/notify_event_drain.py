"""Drain notify_events outbox into NotifyService (sound / Feishu)."""

from __future__ import annotations

import asyncio

import structlog

from media2text.core.config import AppConfig
from media2text.core.notify.drain import drain_once

log = structlog.get_logger()

_DRAIN_INTERVAL_SEC = 1.5

__all__ = ["drain_once", "run_notify_drain_loop"]


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
