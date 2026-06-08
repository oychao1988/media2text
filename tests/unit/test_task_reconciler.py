from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.live.task_reconciler import reconcile_live
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
)


def _setup_creator(conn, *, sec_uid: str) -> str:
    return CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )


def test_scheduler_reconcile_prepare_when_live_no_session(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = _setup_creator(conn, sec_uid="MS4wLjABAAAArec1")
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="1")
    reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"prepare:{cid}")


def test_scheduler_reconcile_finalize_when_offline_confirmed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"offline_confirm_sec": 45})
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = _setup_creator(conn, sec_uid="MS4wLjABAAAArec2")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute(
        "UPDATE live_sessions SET obs_still_live = 0 WHERE id = ?",
        (sid,),
    )
    conn.commit()
    reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")


def test_offline_flash_recovery_cancels_pending_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"offline_confirm_sec": 45})
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = _setup_creator(conn, sec_uid="MS4wLjABAAAArec3")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute(
        "UPDATE live_sessions SET obs_still_live = 0 WHERE id = ?",
        (sid,),
    )
    conn.commit()
    reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")

    conn.execute(
        "UPDATE live_sessions SET obs_still_live = 1 WHERE id = ?",
        (sid,),
    )
    conn.commit()
    reconcile_live(cfg, conn)
    assert not MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")


def test_reconcile_content_ensure_sync_when_vod_due(tmp_path, monkeypatch) -> None:
    from media2text.core.live.task_reconciler import reconcile_content

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAArc1",
        profile_url="https://example.com/u",
        monitor_enabled=True,
        platform="douyin",
    )
    past = datetime.now(timezone.utc).isoformat()
    CreatorRepo(conn).set_vod_due(cid, past)
    reconcile_content(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"sync_catalog:{cid}")
    creator = CreatorRepo(conn).get(cid)
    assert creator is not None
    assert creator.vod_due_at is None
