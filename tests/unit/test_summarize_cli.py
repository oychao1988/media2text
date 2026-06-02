import json
from pathlib import Path

from typer.testing import CliRunner

from media2text.cli.main import app

runner = CliRunner()


def test_summarize_run_json_shape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "media2text.cli.summarize.run_batch",
        lambda *a, **k: {
            "ok": True,
            "command": "summarize run",
            "summarized": 0,
            "skipped": 0,
            "results": [],
            "suggested_groups": [],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "media2text.cli.summarize.summarize_engine_available",
        lambda cfg: (True, None),
    )
    monkeypatch.setattr(
        "media2text.cli.summarize.create_summarize_backend",
        lambda cfg: object(),
    )
    monkeypatch.setattr("media2text.cli.summarize.open_db", lambda cfg: None)

    result = runner.invoke(app, ["summarize", "run", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "suggested_groups" in data
