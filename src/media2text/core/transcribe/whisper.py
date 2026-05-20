from __future__ import annotations

import json
import subprocess
from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.errors import TranscribeError
from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment


def audio_sidecar_path(media_path: Path) -> Path:
    return media_path.with_suffix(".16k.wav")


def should_skip_audio_extract(media_path: Path, sidecar: Path) -> bool:
    if not sidecar.is_file():
        return False
    return sidecar.stat().st_mtime >= media_path.stat().st_mtime


def extract_audio_16k(
    *,
    ffmpeg: str,
    media_path: Path,
    sidecar: Path | None = None,
) -> Path:
    """Extract mono 16 kHz PCM WAV for faster-whisper. Reuses fresh sidecar when present."""
    out = sidecar or audio_sidecar_path(media_path)
    if should_skip_audio_extract(media_path, out):
        return out

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise TranscribeError(
            f"ffmpeg not found ({ffmpeg}); install ffmpeg or set live.ffmpeg_path"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise TranscribeError(
            f"ffmpeg audio extract failed for {media_path.name}"
            + (f": {stderr}" if stderr else "")
        ) from exc

    if not out.is_file() or out.stat().st_size == 0:
        raise TranscribeError(f"ffmpeg produced empty audio sidecar: {out.name}")
    return out


def whisper_backend_from_config(cfg: AppConfig) -> WhisperBackend:
    w = cfg.transcribe.whisper
    return WhisperBackend(
        model=w.model,
        device=w.device,
        compute_type=w.compute_type,
        vad_filter=w.vad_filter,
        extract_audio=w.extract_audio,
        ffmpeg_path=cfg.live.ffmpeg_path,
    )


class WhisperBackend:
    def __init__(
        self,
        *,
        model: str,
        device: str,
        compute_type: str = "int8",
        vad_filter: bool = True,
        extract_audio: bool = True,
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._vad_filter = vad_filter
        self._extract_audio = extract_audio
        self._ffmpeg_path = ffmpeg_path
        self._model = None

    def _resolve_input(self, media_path: Path) -> Path:
        if not self._extract_audio:
            return media_path
        return extract_audio_16k(ffmpeg=self._ffmpeg_path, media_path=media_path)

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def transcribe(self, media_path: Path, *, language: str | None = None) -> TranscriptResult:
        input_path = self._resolve_input(media_path)
        model = self._load_model()
        segments_iter, _info = model.transcribe(
            str(input_path),
            language=language,
            vad_filter=self._vad_filter,
        )
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
