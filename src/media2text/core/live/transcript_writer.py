"""Incremental transcript writer for live streaming STT."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.whisper import write_transcript_outputs


@dataclass
class TranscriptWriter:
    """Accumulate final segments and periodic partial flush."""

    media_path: Path
    engine: str = "deepgram"
    model: str = "nova-3"
    flush_interval_sec: float = 30.0
    _segments: list[TranscriptSegment] = field(default_factory=list)
    _last_flush_mono: float = field(default_factory=time.monotonic)
    _offset_sec: float = 0.0

    @property
    def partial_path(self) -> Path:
        return self.media_path.with_suffix(".transcript.partial.json")

    def add_final(self, text: str, *, start: float, end: float) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self._segments.append(
            TranscriptSegment(
                start=self._offset_sec + start,
                end=self._offset_sec + end,
                text=cleaned,
            )
        )
        self.maybe_flush_partial()

    def maybe_flush_partial(self, *, force: bool = False) -> None:
        if not self._segments:
            return
        now = time.monotonic()
        if not force and (now - self._last_flush_mono) < self.flush_interval_sec:
            return
        self._write_partial()
        self._last_flush_mono = now

    def _write_partial(self) -> None:
        payload = {
            "engine": self.engine,
            "model": self.model,
            "text": "\n".join(s.text for s in self._segments),
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text} for s in self._segments
            ],
            "partial": True,
        }
        self.partial_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_result(self) -> TranscriptResult:
        return TranscriptResult(
            text="\n".join(s.text for s in self._segments),
            segments=list(self._segments),
            engine=self.engine,
            model=self.model,
        )

    def finalize(self) -> tuple[Path, Path]:
        """Write final .transcript.json/.md compatible with batch transcribe."""
        result = self.to_result()
        json_path, md_path = write_transcript_outputs(self.media_path, result)
        self.partial_path.unlink(missing_ok=True)
        return json_path, md_path

    def segment_count(self) -> int:
        return len(self._segments)
