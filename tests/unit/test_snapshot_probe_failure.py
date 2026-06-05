import pytest

from media2text.core.live.snapshot import touch_snapshot_probe_failed, upsert_live_snapshot
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo

pytestmark = pytest.mark.desktop


def test_touch_probe_failed_updates_checked_at_only(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="sec_probe",
        profile_url="https://www.douyin.com/user/sec_probe",
        platform="douyin",
    )
    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    upsert_live_snapshot(conn, cid, live)
    old = LiveSnapshotRepo(conn).get(cid)
    assert old is not None
    old_checked_at = old.checked_at

    touch_snapshot_probe_failed(conn, cid, error="timeout")
    snap = LiveSnapshotRepo(conn).get(cid)
    assert snap is not None
    assert snap.is_live == 1
    assert snap.probe_error == "timeout"
    assert snap.checked_at >= old_checked_at
    conn.close()


def test_upsert_returns_false_when_unchanged(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="sec_unchanged",
        profile_url="https://www.douyin.com/user/sec_unchanged",
        platform="douyin",
    )
    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    assert upsert_live_snapshot(conn, cid, live) is True
    first_checked = LiveSnapshotRepo(conn).get(cid)
    assert first_checked is not None
    later = "2099-01-01T00:00:00+00:00"
    assert (
        LiveSnapshotRepo(conn).upsert(
            cid, is_live=True, room_id="r1", title=None, checked_at=later
        )
        is False
    )
    snap = LiveSnapshotRepo(conn).get(cid)
    assert snap is not None
    assert snap.checked_at == later
    conn.close()


def test_upsert_live_snapshot_none_returns_false(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="sec_none",
        profile_url="https://www.douyin.com/user/sec_none",
        platform="douyin",
    )
    assert upsert_live_snapshot(conn, cid, None) is False
    assert LiveSnapshotRepo(conn).get(cid) is None
    conn.close()
