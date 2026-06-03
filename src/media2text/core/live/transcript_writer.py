"""Incremental transcript writer for live streaming STT."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.whisper import write_transcript_outputs

_SEG_CHECKPOINT_RE = re.compile(r"\.transcript\.seg(\d+)\.json$")


def segment_checkpoint_path(media_path: Path, index: int) -> Path:
    return media_path.parent / f"{media_path.stem}.transcript.seg{index}.json"


def list_segment_checkpoints(media_path: Path) -> list[Path]:
    paths = [
        p
        for p in media_path.parent.glob(f"{media_path.stem}.transcript.seg*.json")
        if p.is_file()
    ]
    return sorted(paths, key=_checkpoint_sort_key)


def _checkpoint_sort_key(path: Path) -> int:
    match = _SEG_CHECKPOINT_RE.search(path.name)
    return int(match.group(1)) if match else 0


def _segments_from_payload(payload: dict) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for raw in payload.get("segments") or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(raw.get("start", 0.0)),
                end=float(raw.get("end", 0.0)),
                text=text,
            )
        )
    return segments


def merge_transcript_checkpoints(
    media_path: Path,
    checkpoint_paths: list[Path],
    *,
    trailing_segments: list[TranscriptSegment] | None = None,
    engine: str = "deepgram",
    model: str = "nova-3",
) -> tuple[Path, Path] | None:
    """Merge segment checkpoint files (+ optional live segments) into final sidecars."""
    merged: list[TranscriptSegment] = []
    resolved_engine = engine
    resolved_model = model
    for path in checkpoint_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        merged.extend(_segments_from_payload(payload))
        resolved_engine = str(payload.get("engine") or resolved_engine)
        resolved_model = str(payload.get("model") or resolved_model)
    if trailing_segments:
        merged.extend(trailing_segments)
    if not merged:
        return None
    merged.sort(key=lambda s: (s.start, s.end))
    result = TranscriptResult(
        text="\n".join(s.text for s in merged),
        segments=merged,
        engine=resolved_engine,
        model=resolved_model,
    )
    paths = write_transcript_outputs(media_path, result)
    partial_path = media_path.with_suffix(".transcript.partial.json")
    partial_path.unlink(missing_ok=True)
    for path in checkpoint_paths:
        path.unlink(missing_ok=True)
    return paths


def count_transcript_segments(media_path: str | Path | None) -> int | None:
    """Return segment count from final or partial sidecar, if present."""
    if not media_path:
        return None
    base = Path(media_path)
    for name in (
        f"{base.stem}.transcript.json",
        f"{base.stem}.transcript.partial.json",
    ):
        sidecar = base.parent / name
        if not sidecar.is_file():
            continue
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        segments = payload.get("segments")
        if isinstance(segments, list):
            return len(segments)
    return None


@dataclass
class TranscriptWriter:
    """Accumulate final segments and periodic partial flush."""

    media_path: Path
    engine: str = "deepgram"
    model: str = "nova-3"
    flush_interval_sec: float = 30.0
    offset_sec: float = 0.0
    _segments: list[TranscriptSegment] = field(default_factory=list, repr=False)
    _last_flush_mono: float = field(default_factory=time.monotonic, repr=False)
    on_partial_summary: Callable[[str, int], None] | None = field(
        default=None, repr=False
    )

    @property
    def partial_path(self) -> Path:
        return self.media_path.with_suffix(".transcript.partial.json")

    def add_final(self, text: str, *, start: float, end: float) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self._segments.append(
            TranscriptSegment(
                start=self.offset_sec + start,
                end=self.offset_sec + end,
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
        if self.on_partial_summary:
            tail = self._segments[-3:]
            summary = "\n".join(s.text for s in tail).strip()
            if summary:
                self.on_partial_summary(summary, len(self._segments))

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

    def current_segments(self) -> list[TranscriptSegment]:
        return list(self._segments)

    def segment_end_sec(self) -> float:
        if not self._segments:
            return self.offset_sec
        return max(s.end for s in self._segments)

    def checkpoint_segment(self, index: int) -> float:
        """Persist segments for one STT run; return timeline offset for the next run."""
        if not self._segments:
            return self.offset_sec
        path = segment_checkpoint_path(self.media_path, index)
        payload = {
            "engine": self.engine,
            "model": self.model,
            "text": "\n".join(s.text for s in self._segments),
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text} for s in self._segments
            ],
            "segment_index": index,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        end = max(s.end for s in self._segments)
        self._segments.clear()
        self.offset_sec = end
        self.partial_path.unlink(missing_ok=True)
        return end


def seal_partial_transcript(media_path: Path) -> tuple[Path, Path] | None:
    """Promote ``.transcript.partial.json`` to final sidecars when STT session is gone."""
    partial_path = media_path.with_suffix(".transcript.partial.json")
    if not partial_path.is_file():
        return None

    json_path = media_path.with_suffix(".transcript.json")
    md_path = media_path.with_suffix(".transcript.md")
    if json_path.is_file():
        partial_path.unlink(missing_ok=True)
        return json_path, md_path

    try:
        payload = json.loads(partial_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    segments: list[TranscriptSegment] = []
    for raw in payload.get("segments") or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(raw.get("start", 0.0)),
                end=float(raw.get("end", 0.0)),
                text=text,
            )
        )

    text = str(payload.get("text") or "").strip()
    if not text and segments:
        text = "\n".join(s.text for s in segments)
    if not text:
        return None

    result = TranscriptResult(
        text=text,
        segments=segments,
        engine=str(payload.get("engine") or "deepgram"),
        model=str(payload.get("model") or "nova-3"),
    )
    paths = write_transcript_outputs(media_path, result)
    partial_path.unlink(missing_ok=True)
    return paths
