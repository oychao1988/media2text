from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def test_poll_increments_offline_streak_before_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAstreak",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAstreak/live/x.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    conn.execute("UPDATE live_sessions SET started_at = ? WHERE id = ?", (old, sid))
    conn.commit()

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="99", is_live=False, stream_flv_url=None
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
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        row = sessions.get(sid)
        assert row is not None
        assert row.offline_streak == 1

        core.poll_active_recordings()
        core.poll_active_recordings()
        assert sessions.get(sid).offline_streak == 3
        mock_fin.assert_called_once()


def test_poll_skips_fresh_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAskip",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = sessions.create(
        creator_id=cid,
        room_id="123",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=4242,
    )

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="123", is_live=False, stream_flv_url=None
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
        patch.object(core, "_finalize_recording") as mock_finalize,
    ):
        core.poll_active_recordings(skip_session_ids={sid})

    mock_finalize.assert_not_called()


def test_ffmpeg_exit_restarts_when_still_live(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAreconn",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAreconn/live/part1.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="99", is_live=True, stream_flv_url="https://example.com/live.flv"
    )
    adapter.resolve_stream_url.return_value = "https://example.com/live2.flv"

    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )

    with (
        patch.object(core, "_process_alive", return_value=False),
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
        patch.object(core, "_finalize_recording") as mock_fin,
    ):
        core.poll_active_recordings()
        mock_fin.assert_not_called()
        row = sessions.get(sid)
        assert row is not None
        assert row.reconnect_attempts == 1
        assert row.ffmpeg_pid == 9999


def test_finalize_enqueues_post_process_job(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    jobs = PostProcessJobRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAenqueue",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAenqueue/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260602T120000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )

    adapter = MagicMock()
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )

    with (
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.recording.refresh_manifest"),
        patch.object(core, "_process_alive", return_value=False),
    ):
        def _fake_remux(**kwargs):
            kwargs["dst"].write_bytes(b"\x00\x00\x00\x18ftyp")

        mock_remux.side_effect = _fake_remux
        meta = core._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    pending = jobs.list_pending(limit=5)
    assert len(pending) == 1
    assert pending[0].session_id == sid
    assert pending[0].mp4_path.endswith(".mp4")
