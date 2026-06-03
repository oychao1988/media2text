from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PipelineEventRepo


def test_streaming_metrics_from_pipeline_events(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    from media2text.core.config import AppConfig
    from media2text.core.workspace import open_db

    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAmetrics",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        pipeline_mode="streaming",
    )
    LiveSessionRepo(conn).update_status(
        sid, status="completed", ended=True
    )
    conn.execute(
        "UPDATE live_sessions SET ended_at = ? WHERE id = ?",
        ("2026-06-03T12:01:00+00:00", sid),
    )
    conn.commit()
    events = PipelineEventRepo(conn)
    events.insert(
        session_id=sid,
        stage="recording",
        status="offline_pending",
        started_at="2026-06-03T12:00:00+00:00",
        ended_at="2026-06-03T12:00:00+00:00",
        duration_ms=0,
    )
    events.insert(
        session_id=sid,
        stage="streaming_stt",
        status="completed",
        started_at="2026-06-03T12:00:30+00:00",
        ended_at="2026-06-03T12:00:35+00:00",
        duration_ms=5000,
    )
    events.insert(
        session_id=sid,
        stage="streaming_stt",
        status="first_final",
        started_at="2026-06-03T12:00:10+00:00",
        ended_at="2026-06-03T12:00:10+00:00",
        duration_ms=8000,
    )

    metrics = events.streaming_metrics_since("2026-06-01T00:00:00+00:00")
    assert metrics["s1_finalize_stt_ms"]["count"] == 1
    assert metrics["s1_finalize_stt_ms"]["p50_ms"] == 5000
    assert metrics["first_final_latency_ms"]["p50_ms"] == 8000
    assert metrics["s2_offline_to_complete_ms"]["count"] == 1
    assert metrics["s2_offline_to_complete_ms"]["p50_ms"] == 60_000

    summaries = LiveSessionRepo(conn).list_streaming_summary_since(
        "2026-06-01T00:00:00+00:00"
    )
    assert len(summaries) == 1
    assert summaries[0]["pipeline_mode"] == "streaming"
