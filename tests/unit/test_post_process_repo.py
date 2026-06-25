from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def test_enqueue_and_claim_job(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAjob",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    job_id = repo.enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "out.mp4"),
    )
    pending = repo.list_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].id == job_id
    assert pending[0].status == "pending"


def test_claim_pending_atomic(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAclaim",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    job_id = repo.enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "out.mp4"),
    )
    claimed = repo.claim_pending(limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == job_id
    assert claimed[0].status == "running"
    again = repo.claim_pending(limit=1)
    assert again == []


def test_retry_failed_resets_to_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAretry",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    job_id = repo.enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "out.mp4"),
    )
    repo.mark_failed(job_id, error="transcribe failed")
    assert repo.retry_failed(job_id) is True
    row = repo.get(job_id)
    assert row is not None
    assert row.status == "pending"
    assert row.error is None
    assert repo.retry_failed(job_id) is False


def test_retry_failed_rejects_non_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAretrypend",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    job_id = repo.enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "out.mp4"),
    )
    assert repo.retry_failed(job_id) is False


def test_ensure_enqueue_dedupes_active_session(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAdedupe",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    first = repo.ensure_enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "a.mp4"),
    )
    second = repo.ensure_enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "b.mp4"),
    )
    assert first == second
    pending = repo.list_pending(limit=10)
    assert len(pending) == 1


def test_post_process_stale_completed_session_marked_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from datetime import datetime, timedelta, timezone
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstalefail",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=1,
    )
    repo = PostProcessJobRepo(conn)
    job_id = repo.enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(tmp_path / "out.mp4"),
    )
    repo.mark_running(job_id)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    conn.execute(
        "UPDATE post_process_jobs SET updated_at = ? WHERE id = ?",
        (stale, job_id),
    )
    conn.execute(
        "UPDATE live_sessions SET status = 'completed', ended_at = ? WHERE id = ?",
        (stale, sid),
    )
    conn.commit()
    reset = repo.reset_stale_running(older_than_sec=60)
    assert reset == 1
    row = repo.get(job_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "superseded:session_terminal"


def test_stale_reconnect_skips_get_active(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAreconnstale",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=999999,
    )
    conn.execute(
        "UPDATE live_sessions SET reconnect_attempts = 1 WHERE id = ?",
        (sid,),
    )
    conn.commit()
    active = LiveSessionRepo(conn).get_active_for_creator(cid)
    assert active is not None
    assert active.reconnect_attempts == 1
