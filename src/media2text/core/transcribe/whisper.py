from __future__ import annotations

import json
from pathlib import Path

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment


class WhisperBackend:
    def __init__(self, *, model: str, device: str) -> None:
        self._model_name = model
        self._device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._model_name, device=self._device)
        return self._model

    def transcribe(self, media_path: Path, *, language: str | None = None) -> TranscriptResult:
        model = self._load_model()
        segments_iter, _info = model.transcribe(str(media_path), language=language)
        segments: list[TranscriptSegment] = []
        lines: list[str] = []
        for seg in segments_iter:
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=seg.text.strip()))
            lines.append(seg.text.strip())
        return TranscriptResult(
            text="\n".join(lines),
            segments=segments,
            engine="whisper",
            model=self._model_name,
        )


def write_transcript_outputs(media_path: Path, result: TranscriptResult) -> tuple[Path, Path]:
    json_path = media_path.with_suffix(".transcript.json")
    md_path = media_path.with_suffix(".transcript.md")
    json_path.write_text(
        json.dumps(
            {
                "engine": result.engine,
                "model": result.model,
                "text": result.text,
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text} for s in result.segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_lines = [f"# Transcript: {media_path.name}", ""]
    for seg in result.segments:
        md_lines.append(f"- [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_path, md_path
