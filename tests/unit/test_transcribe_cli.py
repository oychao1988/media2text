from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from media2text.cli.main import app
from media2text.core.config import AppConfig, TranscribeConfig
from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.errors import TranscribeConfigError


def test_transcribe_run_missing_openai_key_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    cfg = AppConfig(workspace=tmp_path / "data", transcribe=TranscribeConfig(engine="openai"))
    monkeypatch.setattr("media2text.cli.transcribe.AppConfig.load", lambda: cfg)

    with patch(
        "media2text.cli.transcribe.create_transcribe_backend",
        side_effect=TranscribeConfigError("OpenAI API key not set; export OPENAI_API_KEY"),
    ):
        result = CliRunner().invoke(app, ["transcribe", "run", str(media), "--json"])

    assert result.exit_code == 1
    assert '"ok": false' in result.stdout
    assert "OPENAI_API_KEY" in result.stdout
    assert "sk-" not in result.stdout


def test_transcribe_run_success_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    cfg = AppConfig(workspace=tmp_path / "data")
    monkeypatch.setattr("media2text.cli.transcribe.AppConfig.load", lambda: cfg)

    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = TranscriptResult(
        text="hi",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="hi")],
        engine="openai",
        model="whisper-1",
    )

    with patch("media2text.cli.transcribe.create_transcribe_backend", return_value=mock_backend):
        result = CliRunner().invoke(app, ["transcribe", "run", str(media), "--json"])

    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert media.with_suffix(".transcript.json").is_file()
