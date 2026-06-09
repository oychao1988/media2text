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


def test_profile_offline_hls_growth_does_not_block_offline(tmp_path, monkeypatch) -> None:
    core, sid, _flv, notify, adapter = _core(tmp_path, monkeypatch)
    m3u8 = tmp_path / "data/creators/MS4wLjABAAAAflake/live/sess/master.m3u8"
    m3u8.parent.mkdir(parents=True, exist_ok=True)
    parts = m3u8.parent / "parts"
    parts.mkdir()
    seg = parts / "seg-00001.m4s"
    seg.write_bytes(b"x" * 8192)
    m3u8.write_text("#EXTM3U\nseg-00001.m4s\n", encoding="utf-8")
    core._conn.execute(
        "UPDATE live_sessions SET temp_path = ?, session_dir = ? WHERE id = ?",
        (str(m3u8), str(m3u8.parent), sid),
    )
    core._conn.commit()
    adapter.get_room_reflow.return_value = LiveRoomInfo(
        room_id="666198550100",
        is_live=False,
        stream_flv_url=None,
    )
    core._cfg.live.offline_flv_stall_polls = 2

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        notify.emit.assert_called_once()
        assert notify.emit.call_args[0][0].kind == EventKind.LIVE_ENDED
        row = core._sessions.get(sid)
        assert row is not None
        assert row.offline_since_at is not None

        notify.reset_mock()
        seg.write_bytes(b"x" * 16384)
        core.poll_active_recordings()
        notify.emit.assert_not_called()
        mock_fin.assert_not_called()
        row = core._sessions.get(sid)
        assert row is not None
        assert row.offline_since_at is not None


def test_profile_offline_after_flv_stall_ignores_reflow(tmp_path, monkeypatch) -> None:
    core, sid, _flv, notify, adapter = _core(tmp_path, monkeypatch)
    adapter.get_room_reflow.return_value = LiveRoomInfo(
        room_id="666198550100",
        is_live=True,
        stream_flv_url="https://example.com/x.flv",
    )
    core._cfg.live.offline_flv_stall_polls = 3

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_flv_file_growing", return_value=False),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        core.poll_active_recordings()
        notify.emit.assert_not_called()
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        notify.emit.assert_called_once()
        assert notify.emit.call_args[0][0].kind == EventKind.LIVE_ENDED
