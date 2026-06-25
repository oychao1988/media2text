from typer.testing import CliRunner
from unittest.mock import patch

from media2text.cli.main import app


def test_cli_watch_daemon_refuses_when_reconciler_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "workspace: ./data\nmonitor:\n  reconciler_enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))

    runner = CliRunner()
    with patch("media2text.core.monitor.watcher.workspace_lock"):
        result = runner.invoke(app, ["monitor", "watch", "--daemon", "--json"])
    assert result.exit_code == 1
    payload = __import__("json").loads(result.stdout)
    assert payload["ok"] is False
    assert "reconciler_enabled=true" in payload["error"]
