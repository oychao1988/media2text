from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _seed_job(conn, *, attempts: int = 1, status: str = "failed") -> str:
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegretry",
        profile_url="https://x",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path="/tmp/x.m3u8",
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
    )
    jobs = SegmentProcessJobRepo(conn)
    job_id = jobs.enqueue(session_id=sid, part_index=1)
    assert job_id
    conn.execute(
        """
        UPDATE segment_process_jobs
        SET status = ?, attempts = ?, last_error = 'upload_failed'
        WHERE id = ?
        """,
        (status, attempts, job_id),
    )
    conn.commit()
    return job_id


def test_reset_failed_to_pending_when_under_max(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    job_id = _seed_job(conn, attempts=2, status="failed")
    jobs = SegmentProcessJobRepo(conn)

    reset = jobs.reset_failed_to_pending(max_attempts=5)
    assert reset == 1
    row = jobs.get(job_id)
    assert row is not None
    assert row.status == "pending"
    claimed = jobs.claim_pending(limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == job_id


def test_reset_failed_keeps_exhausted_jobs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    job_id = _seed_job(conn, attempts=5, status="failed")
    jobs = SegmentProcessJobRepo(conn)

    reset = jobs.reset_failed_to_pending(max_attempts=5)
    assert reset == 0
    row = jobs.get(job_id)
    assert row is not None
    assert row.status == "failed"


def test_retry_failed_manual_resets_job(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    job_id = _seed_job(conn, attempts=99, status="failed")
    jobs = SegmentProcessJobRepo(conn)

    assert jobs.retry_failed(job_id) is True
    row = jobs.get(job_id)
    assert row is not None
    assert row.status == "pending"
