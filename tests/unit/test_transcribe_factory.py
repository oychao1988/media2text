from __future__ import annotations

from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig, OpenAIConfig, TranscribeConfig
from media2text.core.transcribe.errors import TranscribeConfigError
from media2text.core.transcribe.factory import create_transcribe_backend, transcribe_engine_available
from media2text.core.transcribe.whisper import WhisperBackend


def test_transcribe_engine_available_openai_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = AppConfig(
        transcribe=TranscribeConfig(engine="openai", openai=OpenAIConfig(api_key_env="OPENAI_API_KEY"))
    )
    with patch.dict("sys.modules", {"openai": object()}):
        available, reason = transcribe_engine_available(cfg)
    assert available is False
    assert reason is not None
    assert "OPENAI_API_KEY" in reason


def test_create_transcribe_backend_whisper(monkeypatch) -> None:
    cfg = AppConfig(transcribe=TranscribeConfig(engine="whisper"))
    fake_fw = object()
    with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
        backend = create_transcribe_backend(cfg)
    assert isinstance(backend, WhisperBackend)


def test_create_transcribe_backend_openai(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = AppConfig(transcribe=TranscribeConfig(engine="openai"))
    with patch.dict("sys.modules", {"openai": object()}):
        backend = create_transcribe_backend(cfg)
    assert backend.__class__.__name__ == "OpenAIBackend"


def test_create_transcribe_backend_unsupported() -> None:
    cfg = AppConfig(transcribe=TranscribeConfig(engine="deepgram"))
    with pytest.raises(TranscribeConfigError, match="Unsupported"):
        create_transcribe_backend(cfg)
