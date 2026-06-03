from media2text.core.storage.repos import PipelineEventRepo


def test_pipeline_event_insert_and_complete(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    from media2text.core.config import AppConfig
    from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
    from media2text.core.workspace import open_db

    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAevt",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PipelineEventRepo(conn)
    eid = repo.insert(
        session_id=sid,
        stage="remux",
        status="started",
        started_at="2026-06-03T12:00:00+00:00",
    )
    repo.complete(
        eid,
        status="completed",
        ended_at="2026-06-03T12:00:05+00:00",
        duration_ms=5000,
    )
    rows = repo.list_for_session(sid)
    assert len(rows) == 1
    assert rows[0].stage == "remux"
    assert rows[0].status == "completed"
    assert rows[0].duration_ms == 5000


def test_stage_event_context_manager(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    from media2text.core.config import AppConfig
    from media2text.core.live.pipeline_events import stage_event
    from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
    from media2text.core.workspace import open_db

    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAActx",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    with stage_event(conn, session_id=sid, stage="transcribe", job_id="job-1"):
        pass
    repo = PipelineEventRepo(conn)
    rows = repo.list_for_session(sid)
    assert len(rows) == 1
    assert rows[0].status == "completed"
    assert rows[0].duration_ms is not None
