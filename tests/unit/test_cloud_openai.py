from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.transcribe.cloud_openai import OpenAIBackend
from media2text.core.transcribe.errors import TranscribeConfigError


def test_openai_backend_maps_verbose_json_segments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake")

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = SimpleNamespace(
        text="hello world",
        segments=[
            SimpleNamespace(start=0.0, end=1.2, text="hello"),
            SimpleNamespace(start=1.2, end=2.0, text="world"),
        ],
    )

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    wav = tmp_path / "extracted.wav"
    wav.write_bytes(b"wav")

    def fake_named_tempfile(*_args, **_kwargs):
        handle = MagicMock()
        handle.name = str(wav)
        return handle

    with (
        patch.dict("sys.modules", {"openai": mock_openai}),
        patch(
            "media2text.core.transcribe.cloud_openai.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ),
        patch(
            "media2text.core.transcribe.cloud_openai.tempfile.NamedTemporaryFile",
            side_effect=fake_named_tempfile,
        ),
    ):
        backend = OpenAIBackend(api_key_env="OPENAI_API_KEY", model="whisper-1")
        result = backend.transcribe(media, language="zh")

    mock_openai.OpenAI.assert_called_once_with(api_key="sk-test")
    create_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert create_kwargs["model"] == "whisper-1"
    assert create_kwargs["response_format"] == "verbose_json"
    assert create_kwargs["language"] == "zh"
    assert hasattr(create_kwargs["file"], "read")

    assert result.engine == "openai"
    assert result.model == "whisper-1"
    assert result.text == "hello world"
    assert len(result.segments) == 2
    assert result.segments[0].text == "hello"


def test_openai_backend_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = OpenAIBackend(api_key_env="OPENAI_API_KEY", model="whisper-1")
    with pytest.raises(TranscribeConfigError, match="OPENAI_API_KEY"):
        backend._client()


def test_openai_backend_passes_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_openai = MagicMock()
    with patch.dict("sys.modules", {"openai": mock_openai}):
        OpenAIBackend(
            api_key_env="OPENAI_API_KEY",
            model="whisper-1",
            base_url="https://proxy.example/v1",
        )._client()
    mock_openai.OpenAI.assert_called_once_with(
        api_key="sk-test",
        base_url="https://proxy.example/v1",
    )
