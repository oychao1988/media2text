from typer.testing import CliRunner

from media2text.cli.live import app
from media2text.core.config import AppConfig
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
)


def test_live_status_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAcli",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=4242,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert "active_recordings" in result.stdout
    assert "post_process" in result.stdout
    assert "monitor_tasks" in result.stdout


def test_live_timeline_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAtl",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    PipelineEventRepo(conn).insert(
        session_id=sid,
        stage="recording",
        status="started",
        started_at="2026-06-03T12:00:00+00:00",
        ended_at="2026-06-03T12:00:01+00:00",
        duration_ms=1000,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["timeline", sid, "--json"])
    assert result.exit_code == 0
    assert '"events"' in result.stdout
    assert "recording" in result.stdout
