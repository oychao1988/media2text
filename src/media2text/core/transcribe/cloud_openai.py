from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.errors import TranscribeConfigError, TranscribeError

_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".m4v"}


class OpenAIBackend:
    def __init__(
        self,
        *,
        api_key_env: str,
        model: str,
        base_url: str | None = None,
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._base_url = base_url
        self._ffmpeg_path = ffmpeg_path

    def _api_key(self) -> str:
        key = os.environ.get(self._api_key_env, "").strip()
        if not key:
            raise TranscribeConfigError(
                f"OpenAI API key not set; export {self._api_key_env} and retry."
            )
        return key

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise TranscribeConfigError(
                "OpenAI SDK not installed; run: pip install -e \".[transcribe-cloud]\""
            ) from exc

        kwargs: dict = {"api_key": self._api_key()}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    def _prepare_audio(self, media_path: Path) -> tuple[Path, Path | None]:
        if media_path.suffix.lower() not in _VIDEO_SUFFIXES:
            return media_path, None

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        out = Path(tmp.name)
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise TranscribeConfigError(
                f"ffmpeg not found ({self._ffmpeg_path}); install ffmpeg or set live.ffmpeg_path"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise TranscribeError(
                f"ffmpeg audio extract failed for {media_path.name}"
                + (f": {stderr}" if stderr else "")
            ) from exc
        return out, out

    def transcribe(self, media_path: Path, *, language: str | None = None) -> TranscriptResult:
        audio_path, cleanup = self._prepare_audio(media_path)
        try:
            client = self._client()
            with audio_path.open("rb") as audio_file:
                kwargs: dict = {
                    "file": audio_file,
                    "model": self._model,
                    "response_format": "verbose_json",
                }
                if language:
                    kwargs["language"] = language
                response = client.audio.transcriptions.create(**kwargs)
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)

        segments: list[TranscriptSegment] = []
        raw_segments = getattr(response, "segments", None) or []
        for seg in raw_segments:
            start = float(getattr(seg, "start", 0) or 0)
            end = float(getattr(seg, "end", start) or start)
            text = str(getattr(seg, "text", "") or "").strip()
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))

        full_text = str(getattr(response, "text", "") or "").strip()
        if not full_text and segments:
            full_text = "\n".join(s.text for s in segments)

        return TranscriptResult(
            text=full_text,
            segments=segments,
            engine="openai",
            model=self._model,
        )
