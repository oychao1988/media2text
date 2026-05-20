import json

from typer.testing import CliRunner

from media2text.cli.main import app


def test_doctor_json_missing_ffmpeg(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(c["name"] == "ffmpeg" and not c["ok"] for c in payload["checks"])
