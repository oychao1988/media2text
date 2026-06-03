from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    LIVE_STARTED = "live_started"
    LIVE_START_FAILED = "live_start_failed"
    LIVE_ENDED = "live_ended"
    NEW_AWEME = "new_aweme"
    NEW_ARCHIVE = "new_archive"
    NEW_DYNAMIC = "new_dynamic"
    RECORDING_COMPLETED = "recording_completed"
    TRANSCRIBE_COMPLETED = "transcribe_completed"
    SUMMARIZE_COMPLETED = "summarize_completed"
    UPLOAD_COMPLETED = "upload_completed"
    UPLOAD_FAILED = "upload_failed"
    UPLOAD_SKIPPED = "upload_skipped"
    UPLOAD_CLEANUP = "upload_cleanup"


@dataclass(frozen=True)
class NotifyEvent:
    kind: EventKind
    title: str
    body: str
