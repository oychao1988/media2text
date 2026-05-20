from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    segments: list[TranscriptSegment]
    engine: str
    model: str


class TranscribeBackend(Protocol):
    def transcribe(self, media_path: Path, *, language: str | None = None) -> TranscriptResult: ...
