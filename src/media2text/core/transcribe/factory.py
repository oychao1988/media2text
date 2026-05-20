from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.transcribe.base import TranscribeBackend
from media2text.core.transcribe.cloud_openai import OpenAIBackend
from media2text.core.transcribe.errors import TranscribeConfigError
from media2text.core.transcribe.whisper import WhisperBackend

_SUPPORTED_ENGINES = frozenset({"whisper", "openai"})


def transcribe_engine_available(cfg: AppConfig) -> tuple[bool, str | None]:
    engine = cfg.transcribe.engine
    if engine not in _SUPPORTED_ENGINES:
        return False, f"Unsupported transcribe engine: {engine}"

    if engine == "whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper not installed; pip install -e \".[transcribe]\""
        return True, None

    try:
        import openai  # noqa: F401
    except ImportError:
        return False, "openai SDK not installed; pip install -e \".[transcribe-cloud]\""

    key_env = cfg.transcribe.openai.api_key_env
    import os

    if not os.environ.get(key_env, "").strip():
        return False, f"OpenAI API key not set; export {key_env}"
    return True, None


def create_transcribe_backend(cfg: AppConfig) -> TranscribeBackend:
    engine = cfg.transcribe.engine
    if engine == "whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError as exc:
            raise TranscribeConfigError(
                "faster-whisper not installed; run: pip install -e \".[transcribe]\""
            ) from exc
        return WhisperBackend(
            model=cfg.transcribe.whisper.model,
            device=cfg.transcribe.whisper.device,
        )

    if engine == "openai":
        return OpenAIBackend(
            api_key_env=cfg.transcribe.openai.api_key_env,
            model=cfg.transcribe.openai.model,
            base_url=cfg.transcribe.openai.base_url,
            ffmpeg_path=cfg.live.ffmpeg_path,
        )

    raise TranscribeConfigError(f"Unsupported transcribe engine: {engine}")
