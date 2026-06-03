"""Throttled partial-transcript notifications during streaming STT."""

from __future__ import annotations

import time

from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService


class PartialTranscriptNotifier:
    def __init__(
        self,
        cfg: AppConfig,
        notify: NotifyService,
        *,
        title: str,
    ) -> None:
        self._cfg = cfg
        self._notify = notify
        self._title = title
        self._last_mono: float = 0.0
        self._last_segment_count: int = 0

    def maybe_emit(self, summary: str, *, segment_count: int) -> None:
        if not summary.strip():
            return
        if not self._cfg.notify.enabled:
            return
        if not self._cfg.notify.events.transcribe_partial:
            return
        stt = self._cfg.live.streaming_stt
        now = time.monotonic()
        new_finals = segment_count - self._last_segment_count
        if new_finals < stt.partial_notify_min_finals and (
            not self._last_mono
            or (now - self._last_mono) < stt.partial_notify_interval_sec
        ):
            return
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_PARTIAL,
                title=self._title,
                body=summary[:500],
            )
        )
        self._last_mono = now
        self._last_segment_count = segment_count
