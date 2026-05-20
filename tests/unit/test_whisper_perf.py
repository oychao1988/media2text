from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, WhisperConfig
from media2text.core.errors import TranscribeError
from media2text.core.transcribe.whisper import (
    WhisperBackend,
    audio_sidecar_path,
    extract_audio_16k,
    should_skip_audio_extract,
    whisper_backend_from_config,
)


def test_whisper_config_defaults() -> None:
    w = WhisperConfig()
    assert w.compute_type == "int8"
    assert w.vad_filter is True
    assert w.extract_audio is True


def test_audio_sidecar_path() -> None:
    assert audio_sidecar_path(Path("/data/live/foo.mp4")) == Path("/data/live/foo.16k.wav")


def test_should_skip_when_sidecar_newer(tmp_path: Path) -> None:
    media = tmp_path / "a.mp4"
    sidecar = tmp_path / "a.16k.wav"
    media.write_bytes(b"video")
    sidecar.write_bytes(b"audio")
    media.touch()
    sidecar.touch()
    assert should_skip_audio_extract(media, sidecar) is True


@patch("media2text.core.transcribe.whisper.subprocess.run")
def test_extract_audio_ffmpeg_args(mock_run: MagicMock, tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake")
    sidecar = tmp_path / "clip.16k.wav"

    def _touch_output(*_args, **_kwargs) -> None:
        sidecar.write_bytes(b"wav")

    mock_run.side_effect = _touch_output
    out = extract_audio_16k(ffmpeg="ffmpeg", media_path=media)
    assert out == sidecar
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "16000" in cmd
    assert "-ar" in cmd
    idx_ar = cmd.index("-ar")
    assert cmd[idx_ar + 1] == "16000"


@patch("media2text.core.transcribe.whisper.subprocess.run")
def test_extract_audio_skips_when_sidecar_fresh(mock_run: MagicMock, tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    sidecar = tmp_path / "clip.16k.wav"
    media.write_bytes(b"v")
    sidecar.write_bytes(b"a")
    media.touch()
    sidecar.touch()
    out = extract_audio_16k(ffmpeg="ffmpeg", media_path=media)
    assert out == sidecar
    mock_run.assert_not_called()


def test_whisper_model_uses_compute_type(tmp_path: Path) -> None:
    mock_whisper_cls = MagicMock()
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], None)
    mock_whisper_cls.return_value = mock_model
    fake_fw = MagicMock(WhisperModel=mock_whisper_cls)

    wav = tmp_path / "only.wav"
    wav.write_bytes(b"x")
    backend = WhisperBackend(
        model="small",
        device="cpu",
        compute_type="int8",
        vad_filter=True,
        extract_audio=False,
    )
    with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
        backend.transcribe(wav, language="zh")

    mock_whisper_cls.assert_called_once_with("small", device="cpu", compute_type="int8")
    mock_model.transcribe.assert_called_once()
    assert mock_model.transcribe.call_args.kwargs["vad_filter"] is True


@patch("media2text.core.transcribe.whisper.extract_audio_16k")
def test_whisper_extract_audio_before_transcribe(
    mock_extract: MagicMock,
    tmp_path: Path,
) -> None:
    media = tmp_path / "live.mp4"
    media.write_bytes(b"mp4")
    sidecar = tmp_path / "live.16k.wav"
    sidecar.write_bytes(b"wav")
    mock_extract.return_value = sidecar

    mock_whisper_cls = MagicMock()
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], None)
    mock_whisper_cls.return_value = mock_model
    fake_fw = MagicMock(WhisperModel=mock_whisper_cls)

    backend = WhisperBackend(
        model="base",
        device="cpu",
        extract_audio=True,
        ffmpeg_path="ffmpeg",
    )
    with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
        backend.transcribe(media)

    mock_extract.assert_called_once_with(ffmpeg="ffmpeg", media_path=media)
    assert mock_model.transcribe.call_args[0][0] == str(sidecar)


def test_extract_audio_ffmpeg_missing_raises(tmp_path: Path) -> None:
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    with patch(
        "media2text.core.transcribe.whisper.subprocess.run",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(TranscribeError, match="ffmpeg not found"):
            extract_audio_16k(ffmpeg="missing-ffmpeg", media_path=media)


def test_whisper_backend_from_config() -> None:
    cfg = AppConfig()
    cfg.live.ffmpeg_path = "/usr/bin/ffmpeg"
    cfg.transcribe.whisper.compute_type = "float32"
    backend = whisper_backend_from_config(cfg)
    assert backend._compute_type == "float32"
    assert backend._ffmpeg_path == "/usr/bin/ffmpeg"
