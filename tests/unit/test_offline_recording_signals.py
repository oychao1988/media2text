from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.notify.events import EventKind
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _core(tmp_path, monkeypatch) -> tuple:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAflake",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAflake/live/x.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 8192)
    sid = sessions.create(
        creator_id=cid,
        room_id="666198550100",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    conn.execute("UPDATE live_sessions SET started_at = ? WHERE id = ?", (old, sid))
    conn.commit()

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id=None, is_live=False, stream_flv_url=None
    )
    notify = MagicMock()
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=notify,
    )
    return core, sid, flv, notify, adapter


def test_profile_offline_ignored_when_flv_growing(tmp_path, monkeypatch) -> None:
    core, sid, flv, notify, _adapter = _core(tmp_path, monkeypatch)

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        flv.write_bytes(b"x" * 16384)
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        notify.emit.assert_not_called()


def test_profile_offline_ignored_when_reflow_live(tmp_path, monkeypatch) -> None:
    core, sid, flv, notify, adapter = _core(tmp_path, monkeypatch)
    adapter.get_room_reflow.return_value = LiveRoomInfo(
        room_id="666198550100",
        is_live=True,
        stream_flv_url="https://example.com/x.flv",
    )

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_flv_file_growing", return_value=False),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        notify.emit.assert_not_called()


def test_profile_offline_still_finalizes_when_no_signals(tmp_path, monkeypatch) -> None:
    core, sid, _flv, notify, adapter = _core(tmp_path, monkeypatch)
    adapter.get_room_reflow.return_value = LiveRoomInfo(
        room_id="666198550100",
        is_live=False,
        stream_flv_url=None,
    )

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_flv_file_growing", return_value=False),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        notify.emit.assert_called_once()
        assert notify.emit.call_args[0][0].kind == EventKind.LIVE_ENDED
