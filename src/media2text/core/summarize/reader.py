from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from media2text.core.summarize.errors import SummarizeError


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptDoc:
    source_path: Path
    segments: list[TranscriptSegment]
    plain_text: str
    kind: str  # "segments" | "markdown"


def transcript_path_for_media(media: Path) -> Path:
    if media.name.endswith(".transcript.json"):
        return media
    return media.with_suffix(".transcript.json")


def load_transcript(path: Path) -> TranscriptDoc:
    if not path.is_file():
        raise SummarizeError(f"transcript not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    segments: list[TranscriptSegment] = []
    for raw in data.get("segments") or []:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(raw.get("start") or 0),
                end=float(raw.get("end") or 0),
                text=text,
            )
        )
    if not segments:
        plain = str(data.get("text") or "").strip()
        if not plain:
            raise SummarizeError("empty_transcript")
        return TranscriptDoc(
            source_path=path,
            segments=[],
            plain_text=plain,
            kind="segments",
        )
    plain_text = "\n".join(s.text for s in segments)
    return TranscriptDoc(
        source_path=path,
        segments=segments,
        plain_text=plain_text,
        kind="segments",
    )


def load_content_md(path: Path) -> TranscriptDoc:
    if not path.is_file():
        raise SummarizeError(f"content not found: {path}")
    body = path.read_text(encoding="utf-8").strip()
    if not body:
        raise SummarizeError("empty_transcript")
    return TranscriptDoc(
        source_path=path,
        segments=[],
        plain_text=body,
        kind="markdown",
    )
