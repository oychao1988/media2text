import json

import pytest
from typer.testing import CliRunner

from media2text.agent.run_agent import agent_app

pytestmark = pytest.mark.agent

runner = CliRunner()


def test_curator_status_and_dry_run(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(f"workspace: {ws}\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    monkeypatch.chdir(tmp_path)

    status = runner.invoke(agent_app, ["curator", "status"])
    assert status.exit_code == 0
    payload = json.loads(status.stdout)
    assert payload["enabled"] is False

    dry = runner.invoke(agent_app, ["curator", "run", "--dry-run"])
    assert dry.exit_code == 0
    report = json.loads(dry.stdout)
    assert report["dry_run"] is True


def test_curator_pin_unpin(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(f"workspace: {ws}\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    monkeypatch.chdir(tmp_path)

    pin = runner.invoke(agent_app, ["curator", "pin", "my-skill"])
    assert pin.exit_code == 0

    unpin = runner.invoke(agent_app, ["curator", "unpin", "my-skill"])
    assert unpin.exit_code == 0


def test_curator_rollback_list(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(f"workspace: {ws}\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    monkeypatch.chdir(tmp_path)

    out = runner.invoke(agent_app, ["curator", "rollback", "--list"])
    assert out.exit_code == 0
    data = json.loads(out.stdout)
    assert "backups" in data
