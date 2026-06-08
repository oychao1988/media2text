"""E2E-style reconciler timeline: is_live → prepare → offline → finalize."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.task_reconciler import reconcile_live
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
)


def test_reconciler_timeline_prepare_offline_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(offline_confirm_sec=10, min_recording_sec_before_offline_end=0),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAe2e",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )

    # RR-01: snapshot is_live → prepare
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="room1")
    reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"prepare:{cid}")

    # Active session + offline obs → live_ended then finalize after confirm
    flv = tmp_path / "data/creators/MS4wLjABAAAAe2e/live/x.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 8192)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="room1",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    conn.execute("UPDATE live_sessions SET started_at = ? WHERE id = ?", (old, sid))
    conn.commit()

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="room1", is_live=False, stream_flv_url=None
    )
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=False),
    ):
        core.poll_active_recordings()
        row = LiveSessionRepo(conn).get(sid)
        assert row is not None
        assert row.offline_since_at is not None

        past_offline = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
        conn.execute(
            "UPDATE live_sessions SET offline_since_at = ?, obs_still_live = 0 WHERE id = ?",
            (past_offline, sid),
        )
        conn.commit()
        reconcile_live(cfg, conn)

    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")
