import json
from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo


def test_enqueue_and_claim_task(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAmtask",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=cid,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid}",
        priority=10,
        payload_json=json.dumps({"platform": "douyin"}),
    )
    assert task_id is not None
    row = repo.get(task_id)
    assert row is not None
    assert row.status == "pending"
    assert row.task_type == "sync_catalog"


def test_claim_pending_atomic(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAclaim2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=cid,
        task_type="download",
        dedupe_key=f"download:{cid}",
    )
    assert task_id is not None
    claimed = repo.claim_pending(limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == task_id
    assert claimed[0].status == "running"
    again = repo.claim_pending(limit=1)
    assert again == []


def test_dedupe_active_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAdedupe",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    dedupe = f"sync_catalog:{cid}"
    first = repo.enqueue(
        creator_id=cid,
        task_type="sync_catalog",
        dedupe_key=dedupe,
    )
    second = repo.enqueue(
        creator_id=cid,
        task_type="sync_catalog",
        dedupe_key=dedupe,
    )
    assert first is not None
    assert second is None


def test_mark_done_and_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstatus",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=cid,
        task_type="sync_dynamic",
        dedupe_key=f"sync_dynamic:{cid}",
    )
    assert task_id is not None
    repo.claim_pending(limit=1)
    repo.mark_failed(task_id, error="boom")
    row = repo.get(task_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "boom"

    task_id2 = repo.enqueue(
        creator_id=cid,
        task_type="sync_dynamic",
        dedupe_key=f"sync_dynamic2:{cid}",
    )
    assert task_id2 is not None
    repo.claim_pending(limit=1)
    repo.mark_done(task_id2)
    row2 = repo.get(task_id2)
    assert row2 is not None
    assert row2.status == "done"


def test_reset_stale_running(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstale",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=cid,
        task_type="download",
        dedupe_key=f"download:{cid}",
    )
    assert task_id is not None
    repo.claim_pending(limit=1)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    conn.execute(
        "UPDATE monitor_tasks SET started_at = ? WHERE id = ?",
        (old, task_id),
    )
    conn.commit()
    reset = repo.reset_stale_running(older_than_sec=3600)
    assert reset == 1
    row = repo.get(task_id)
    assert row is not None
    assert row.status == "pending"


def test_claim_priority_filters(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAprio",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    fin_id = repo.enqueue(
        creator_id=cid,
        task_type="finalize",
        dedupe_key="finalize:s1",
        priority=0,
        payload_json=json.dumps({"session_id": "s1"}),
    )
    sync_id = repo.enqueue(
        creator_id=cid,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid}",
        priority=10,
    )
    assert fin_id is not None
    assert sync_id is not None

    p0 = repo.claim_pending(limit=1, max_priority=0)
    assert len(p0) == 1
    assert p0[0].id == fin_id

    p10 = repo.claim_pending(limit=1, min_priority=1)
    assert len(p10) == 1
    assert p10[0].id == sync_id
