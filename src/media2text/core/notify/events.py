from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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
    summary: str | None = None
    media_path: Path | None = None
    transcript_path: Path | None = None
    image_path: Path | None = None
    link_url: str | None = None
