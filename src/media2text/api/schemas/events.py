"""WebSocket event types for desktop `/api/events` hub."""

from __future__ import annotations

from enum import Enum
from typing import Any


class EventType(str, Enum):
    PING = "ping"
    DAEMON_STARTED = "daemon.started"
    DAEMON_STOPPED = "daemon.stopped"
    RECORDING_STARTED = "recording.started"
    RECORDING_STOPPED = "recording.stopped"
    CREATOR_UPDATED = "creator.updated"


def event_payload(
    event_type: EventType | str,
    *,
    creator_id: str | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": event_type.value if isinstance(event_type, EventType) else event_type,
    }
    if creator_id is not None:
        payload["creator_id"] = creator_id
    if session_id is not None:
        payload["session_id"] = session_id
    if extra:
        payload.update(extra)
    return payload
