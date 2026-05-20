from __future__ import annotations

import os
from pathlib import Path

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.errors import TranscribeConfigError, TranscribeError
from media2text.core.transcribe.text_postprocess import postprocess_transcript_result
from media2text.core.transcribe.whisper import extract_audio_16k

_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".m4v"}


class DeepgramBackend:
    """Deepgram prerecorded (REST) transcription via official deepgram-sdk."""

    def __init__(
        self,
        *,
        api_key_env: str,
        model: str,
        ffmpeg_path: str = "ffmpeg",
        extract_audio: bool = True,
        smart_format: bool = True,
        punctuate: bool = True,
        utterances: bool = True,
        diarize: bool = False,
        timeout_sec: float = 600.0,
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._ffmpeg_path = ffmpeg_path
        self._extract_audio = extract_audio
        self._smart_format = smart_format
        self._punctuate = punctuate
        self._utterances = utterances
        self._diarize = diarize
        self._timeout_sec = timeout_sec

    def _api_key(self) -> str:
        key = os.environ.get(self._api_key_env, "").strip()
        if not key:
            raise TranscribeConfigError(
                f"Deepgram API key not set; export {self._api_key_env} and retry."
            )
        return key

    def _client(self):
        try:
            from deepgram import DeepgramClient
        except ImportError as exc:
            raise TranscribeConfigError(
                "deepgram-sdk not installed; run: pip install -e \".[transcribe-deepgram]\""
            ) from exc

        return DeepgramClient(api_key=self._api_key(), timeout=self._timeout_sec)

    def _prepare_upload(self, media_path: Path) -> tuple[Path, bool]:
        """Return (path_to_upload, is_temporary_sidecar)."""
        if self._extract_audio and media_path.suffix.lower() in _VIDEO_SUFFIXES:
            sidecar = extract_audio_16k(ffmpeg=self._ffmpeg_path, media_path=media_path)
            return sidecar, False
        return media_path, False

    def transcribe(self, media_path: Path, *, language: str | None = None) -> TranscriptResult:
        upload_path, _ = self._prepare_upload(media_path)
        if not upload_path.is_file() or upload_path.stat().st_size == 0:
            raise TranscribeError(f"no audio to transcribe: {upload_path.name}")

        client = self._client()
        try:
            response = client.listen.v1.media.transcribe_file(
                request=upload_path.read_bytes(),
                model=self._model,
                language=language,
                smart_format=self._smart_format,
                punctuate=self._punctuate,
                utterances=self._utterances,
                diarize=self._diarize,
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscribeError(f"Deepgram transcribe failed for {media_path.name}: {exc}") from exc

        raw = _response_to_result(response, engine="deepgram", model=self._model)
        return postprocess_transcript_result(
            raw,
            normalize_segments=not self._smart_format,
            sentence_lines=self._punctuate,
        )


def _response_to_result(response, *, engine: str, model: str) -> TranscriptResult:
    results = getattr(response, "results", None)
    if results is None:
        raise TranscribeError("Deepgram response missing results")

    channels = getattr(results, "channels", None) or []
    if not channels:
        raise TranscribeError("Deepgram response has no channels")

    alt = channels[0].alternatives[0]
    segments: list[TranscriptSegment] = []

    utterances = getattr(results, "utterances", None) or []
    for utt in utterances:
        text = (getattr(utt, "transcript", None) or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(getattr(utt, "start", 0) or 0),
                end=float(getattr(utt, "end", 0) or 0),
                text=text,
            )
        )

    full_text = (getattr(alt, "transcript", None) or "").strip()
    if not segments and full_text:
        end = 0.0
        words = getattr(alt, "words", None) or []
        if words:
            end = float(getattr(words[-1], "end", 0) or 0)
        segments.append(TranscriptSegment(start=0.0, end=end, text=full_text))

    if not full_text and segments:
        full_text = "\n".join(s.text for s in segments)
    if not full_text:
        raise TranscribeError("Deepgram returned empty transcript")

    return TranscriptResult(text=full_text, segments=segments, engine=engine, model=model)
