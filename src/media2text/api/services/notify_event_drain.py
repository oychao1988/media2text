"""Drain notify_events outbox into NotifyService (sound / Feishu)."""

from __future__ import annotations

import asyncio

import structlog

from media2text.api.services.drain_interval import resolve_drain_interval_sec
from media2text.core.config import AppConfig
from media2text.core.notify.drain import drain_once
from media2text.core.runtime.supervisor import MonitorSupervisor

log = structlog.get_logger()

__all__ = ["drain_once", "run_notify_drain_loop"]


async def run_notify_drain_loop(
    cfg: AppConfig,
    stop: asyncio.Event,
    *,
    supervisor: MonitorSupervisor | None = None,
) -> None:
    while not stop.is_set():
        try:
            drain_once(cfg)
        except Exception:
            log.exception("notify_event_drain_failed")
        interval = resolve_drain_interval_sec(cfg, supervisor=supervisor)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
