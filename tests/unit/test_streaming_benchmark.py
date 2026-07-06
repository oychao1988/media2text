import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from media2text.cli.creator import app as creator_app
from media2text.cli.live import app as live_app
from media2text.core.config import AppConfig
from media2text.core.live.streaming_benchmark import (
    DEFAULT_STREAMING_TARGETS_MS,
    check_streaming_targets,
)
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PipelineEventRepo


def test_check_streaming_targets_pass() -> None:
    metrics = {
        "s1_finalize_stt_ms": {"count": 2, "p95_ms": 8_000},
        "s2_offline_to_complete_ms": {"count": 2, "p95_ms": 40_000},
        "first_final_latency_ms": {"count": 2, "p95_ms": 25_000},
    }
    result = check_streaming_targets(metrics)
    assert result["passed"] is True
    assert result["violations"] == []
    assert len(result["checked"]) == 3
    assert result["insufficient_data"] is False


def test_check_streaming_targets_fail_with_violations() -> None:
    metrics = {
        "s1_finalize_stt_ms": {"count": 1, "p95_ms": 15_000},
        "s2_offline_to_complete_ms": {"count": 1, "p95_ms": 30_000},
        "first_final_latency_ms": {"count": 1, "p95_ms": 45_000},
    }
    result = check_streaming_targets(metrics)
    assert result["passed"] is False
    assert len(result["violations"]) == 2
    by_metric = {v["metric"]: v for v in result["violations"]}
    assert by_metric["s1_finalize_stt_ms"]["over_by_ms"] == 5_000
    assert by_metric["first_final_latency_ms"]["over_by_ms"] == 15_000


def test_check_streaming_targets_skips_missing_s3_metric() -> None:
    metrics = {
        "s1_finalize_stt_ms": {"count": 1, "p95_ms": 5_000},
    }
    result = check_streaming_targets(metrics)
    assert result["passed"] is True
    skipped = {s["metric"]: s["reason"] for s in result["skipped"]}
    assert skipped["s2_offline_to_complete_ms"] == "not_available"
    assert skipped["s3_offline_to_summarize_ms"] == "not_available"
    assert skipped["first_final_latency_ms"] == "not_available"


def test_check_streaming_targets_insufficient_data_exits_ok() -> None:
    result = check_streaming_targets({})
    assert result["passed"] is True
    assert result["insufficient_data"] is True
    assert result["checked"] == []


def test_check_streaming_targets_s3_when_present() -> None:
    metrics = {
        "s3_offline_to_summarize_ms": {"count": 1, "p95_ms": 200_000},
    }
    result = check_streaming_targets(metrics)
    assert result["passed"] is False
    assert result["violations"][0]["metric"] == "s3_offline_to_summarize_ms"
    assert result["violations"][0]["over_by_ms"] == 20_000


def test_live_stats_check_targets_pass(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAgate",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        pipeline_mode="streaming",
    )
    now = datetime.now(timezone.utc).isoformat()
    PipelineEventRepo(conn).insert(
        session_id=sid,
        stage="streaming_stt",
        status="first_final",
        started_at=now,
        ended_at=now,
        duration_ms=5_000,
    )

    runner = CliRunner()
    result = runner.invoke(
        live_app, ["stats", "--days", "7", "--json", "--check-targets"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["streaming"]["target_check"]["passed"] is True
    assert "s3_offline_to_summarize_p95" in payload["streaming"]["targets_ms"]


def test_live_stats_check_targets_fail_exit_code(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAfail",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "y.flv"),
        pipeline_mode="streaming",
    )
    now = datetime.now(timezone.utc).isoformat()
    PipelineEventRepo(conn).insert(
        session_id=sid,
        stage="streaming_stt",
        status="first_final",
        started_at=now,
        ended_at=now,
        duration_ms=60_000,
    )

    runner = CliRunner()
    result = runner.invoke(
        live_app, ["stats", "--days", "7", "--json", "--check-targets"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["target_violations"]


def test_live_stats_check_targets_requires_json() -> None:
    runner = CliRunner()
    result = runner.invoke(live_app, ["stats", "--check-targets"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"] == "check_targets_requires_json"


def test_creator_show_latest_live_session(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAshow",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "z.flv"),
        pipeline_mode="streaming",
    )
    sessions = LiveSessionRepo(conn)
    latest_id = sessions.create(
        creator_id=cid,
        room_id="2",
        temp_path=str(tmp_path / "w.flv"),
        pipeline_mode="legacy",
    )
    sessions.update_status(latest_id, transcribe_status="completed")

    runner = CliRunner()
    result = runner.invoke(creator_app, ["show", cid, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    latest = payload["creator"]["latest_live_session"]
    assert latest["session_id"] == latest_id
    assert latest["pipeline_mode"] == "legacy"
    assert latest["transcribe_status"] == "completed"


def test_creator_show_no_live_session_null(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAempty",
        profile_url="https://example.com/u",
        monitor_enabled=False,
    )

    runner = CliRunner()
    result = runner.invoke(creator_app, ["show", cid, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["creator"]["latest_live_session"] is None


def test_default_targets_include_s3() -> None:
    assert DEFAULT_STREAMING_TARGETS_MS["s3_offline_to_summarize_p95"] == 180_000
