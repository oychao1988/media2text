from typer.testing import CliRunner

from media2text.cli.live import app
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PipelineEventRepo


def test_live_stats_includes_streaming_block(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstats",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        pipeline_mode="streaming",
    )
    LiveSessionRepo(conn).update_status(sid, transcribe_status="streaming")
    PipelineEventRepo(conn).insert(
        session_id=sid,
        stage="streaming_stt",
        status="first_final",
        started_at="2026-06-03T12:00:00+00:00",
        ended_at="2026-06-03T12:00:00+00:00",
        duration_ms=12_000,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["stats", "--days", "7", "--json"])
    assert result.exit_code == 0
    assert '"streaming"' in result.stdout
    assert "first_final_latency_ms" in result.stdout
    assert "transcript_segment_count" in result.stdout or "sessions" in result.stdout
