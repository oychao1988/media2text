"""Push runtime health diffs over WebSocket (desktop EventsHub)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import FastAPI

from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services.events_hub import events_hub
from media2text.api.services.runtime import get_runtime_status
from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SEC = 1.5
_CURATOR_IDLE_TICK_EVERY = 60
_curator_tick_counter = 0


def runtime_ws_payload(full: dict[str, Any]) -> dict[str, Any]:
    """Compact snapshot for WS (diff baseline / heartbeat)."""
    daemon = full.get("daemon") or {}
    recordings = full.get("recordings") or {}
    return {
        "health": full.get("health"),
        "health_reasons": full.get("health_reasons") or [],
        "managed_by": full.get("managed_by"),
        "daemon": {
            "running": daemon.get("running"),
            "pid": daemon.get("pid"),
            "lock_pid": daemon.get("lock_pid"),
            "last_tick_at": daemon.get("last_tick_at"),
            "tick_age_sec": daemon.get("tick_age_sec"),
            "live_poll_interval_sec": daemon.get("live_poll_interval_sec"),
        },
        "recordings": {"active_count": recordings.get("active_count", 0)},
        "queues": full.get("queues") or {},
        "observability": full.get("observability") or {},
    }


def runtime_ws_diff(prev: dict[str, Any] | None, curr: dict[str, Any]) -> dict[str, Any] | None:
    """Return diff fields when meaningful change detected; None if unchanged."""
    if prev is None:
        return curr
    diff: dict[str, Any] = {}
    for key in ("health", "managed_by"):
        if prev.get(key) != curr.get(key):
            diff[key] = curr.get(key)
    if prev.get("health_reasons") != curr.get("health_reasons"):
        diff["health_reasons"] = curr.get("health_reasons")
    prev_daemon = prev.get("daemon") or {}
    curr_daemon = curr.get("daemon") or {}
    daemon_diff: dict[str, Any] = {}
    for field in ("running", "pid", "lock_pid", "last_tick_at"):
        if prev_daemon.get(field) != curr_daemon.get(field):
            daemon_diff[field] = curr_daemon.get(field)
    if daemon_diff:
        diff["daemon"] = daemon_diff
    prev_rec = (prev.get("recordings") or {}).get("active_count")
    curr_rec = (curr.get("recordings") or {}).get("active_count")
    if prev_rec != curr_rec:
        diff["recordings"] = curr.get("recordings")
    if prev.get("queues") != curr.get("queues"):
        diff["queues"] = curr.get("queues")
    prev_obs = prev.get("observability") or {}
    curr_obs = curr.get("observability") or {}
    if prev_obs != curr_obs:
        diff["observability"] = curr_obs
    return diff or None


def publish_runtime_health(extra: dict[str, Any]) -> None:
    events_hub.publish(event_payload(EventType.RUNTIME_HEALTH, extra=extra))


def publish_queue_updated(extra: dict[str, Any]) -> None:
    events_hub.publish(event_payload(EventType.QUEUE_UPDATED, extra=extra))


def drain_runtime_health_once(
    app: FastAPI,
    cfg: AppConfig,
    *,
    prev_payload: dict[str, Any] | None,
    last_publish_at: float,
    heartbeat_sec: float,
) -> tuple[dict[str, Any], float]:
    """One iteration: read runtime, publish WS diffs; return (new_prev, new_last_publish_at)."""
    supervisor: MonitorSupervisor | None = getattr(app.state, "supervisor", None)
    full = get_runtime_status(cfg, supervisor)
    curr = runtime_ws_payload(full)
    now = time.monotonic()
    diff = runtime_ws_diff(prev_payload, curr)
    queues_changed = prev_payload is not None and prev_payload.get("queues") != curr.get("queues")
    heartbeat_due = (now - last_publish_at) >= heartbeat_sec

    if diff is not None:
        publish_runtime_health(diff)
        last_publish_at = now
    elif heartbeat_due:
        publish_runtime_health(curr)
        last_publish_at = now

    if queues_changed and curr.get("queues"):
        publish_queue_updated({"queues": curr["queues"]})

    return curr, last_publish_at


async def run_runtime_health_loop(app: FastAPI, cfg: AppConfig, stop: asyncio.Event) -> None:
    global _curator_tick_counter
    prev: dict[str, Any] | None = None
    last_publish_at = 0.0
    last_self_heal_check = 0.0
    heartbeat_sec = float(cfg.desktop.runtime_ws_interval_sec)
    while not stop.is_set():
        try:
            prev, last_publish_at = drain_runtime_health_once(
                app,
                cfg,
                prev_payload=prev,
                last_publish_at=last_publish_at,
                heartbeat_sec=heartbeat_sec,
            )
            now = time.monotonic()
            if now - last_self_heal_check >= float(cfg.desktop.monitor_self_heal_check_every_sec):
                last_self_heal_check = now
                supervisor: MonitorSupervisor | None = getattr(app.state, "supervisor", None)
                if supervisor is not None:
                    from media2text.api.services.monitor_self_heal import maybe_self_heal_monitor

                    maybe_self_heal_monitor(cfg, supervisor)
            _curator_tick_counter += 1
            if _curator_tick_counter >= _CURATOR_IDLE_TICK_EVERY:
                _curator_tick_counter = 0
                from media2text.agent.curator import maybe_run_curator_idle
                from media2text.agent.turn_registry import turn_registry

                maybe_run_curator_idle(cfg, active_turns=turn_registry.active_count())
        except Exception:
            logger.exception("runtime health loop iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=_LOOP_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue
