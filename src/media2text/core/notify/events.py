from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    LIVE_STARTED = "live_started"
    NEW_AWEME = "new_aweme"
    RECORDING_COMPLETED = "recording_completed"
    TRANSCRIBE_COMPLETED = "transcribe_completed"


@dataclass(frozen=True)
class NotifyEvent:
    kind: EventKind
    title: str
    body: str
