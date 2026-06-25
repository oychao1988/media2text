from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.live.g1_benchmark import compute_g1_detected_to_recording_ms
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PipelineEventRepo
from media2text.core.workspace import open_db


def test_g1_detected_to_recording_p95_mock_under_threshold(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAg1",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=1,
    )
    events = PipelineEventRepo(conn)
    base = datetime.now(timezone.utc)
    detected = base.isoformat()
    recording = (base + timedelta(seconds=5)).isoformat()
    events.insert(
        session_id=sid,
        stage="detected_live",
        status="completed",
        started_at=detected,
        ended_at=detected,
        duration_ms=0,
    )
    events.insert(
        session_id=sid,
        stage="recording",
        status="started",
        started_at=recording,
    )

    summary = compute_g1_detected_to_recording_ms(conn)
    assert summary["sample_count"] == 1
    assert summary["p95_ms"] == 5000
    assert summary["p95_ms"] <= summary["threshold_ms"]
