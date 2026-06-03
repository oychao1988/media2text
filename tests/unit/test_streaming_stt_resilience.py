from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
)


def _streaming_cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            remux_on_complete=False,
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )


def test_ffmpeg_reconnect_marks_degraded_and_legacy_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _streaming_cfg(tmp_path)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAreconn_stt",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAreconn_stt/live"
    live_dir.mkdir(parents=True)
    seg = live_dir / "20260603T120000Z.flv"
    seg.write_bytes(b"x" * 128)
    seg2 = live_dir / "20260603T120100Z_r1.flv"
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(seg2),
        ffmpeg_pid=4242,
    )
    sessions.append_segment_path(sid, str(seg))
    seg2.write_bytes(b"y" * 128)

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="99",
        is_live=True,
        stream_flv_url="https://example.com/live2.flv",
    )

    mock_stt = MagicMock()
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = mock_stt

    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    with (
        patch("media2text.core.live.recording.stop_process"),
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
    ):
        core._reconnect_segment(sid, creators.get(cid), str(seg), 4242)

    assert sid in core._streaming_legacy_finalize
    events = PipelineEventRepo(conn).list_for_session(sid)
    assert ("streaming_stt", "degraded") in {(e.stage, e.status) for e in events}
    mock_stt.stop.assert_called_once()

    with (
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.recording.concat_to_mp4") as mock_concat,
        patch("media2text.core.live.recording.refresh_manifest"),
    ):
        core._finalize_recording(sid, str(seg2), 9999)

    mock_remux.assert_not_called()
    mock_concat.assert_called_once()


def test_stt_disconnect_degrades_when_reconnect_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=False),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAstt_off",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAstt_off/live/x.flv"
    flv.parent.mkdir(parents=True)
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    row = sessions.get(sid)
    creator = creators.get(cid)

    mock_stt = MagicMock()
    mock_stt.is_alive.return_value = False
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = mock_stt
    core._stream_urls[sid] = "https://example.com/live.flv"

    core._handle_stt_disconnect(row, creator)

    assert sid in core._streaming_legacy_finalize
    assert sid not in core._stt_sessions
    events = PipelineEventRepo(conn).list_for_session(sid)
    assert ("streaming_stt", "degraded") in {(e.stage, e.status) for e in events}


def test_stt_disconnect_restarts_when_reconnect_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _streaming_cfg(tmp_path)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAstt_retry",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAstt_retry/live/x.flv"
    flv.parent.mkdir(parents=True)
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    row = sessions.get(sid)
    creator = creators.get(cid)

    dead_stt = MagicMock()
    dead_stt.is_alive.return_value = False
    new_stt = MagicMock()
    new_stt.is_alive.return_value = True

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = dead_stt
    core._stream_urls[sid] = "https://example.com/live.flv"

    with patch(
        "media2text.core.live.recording.StreamingSttSession",
        return_value=new_stt,
    ):
        core._handle_stt_disconnect(row, creator)

    assert sid not in core._streaming_legacy_finalize
    assert core._stt_sessions[sid] is new_stt
    new_stt.start.assert_called_once()
    events = PipelineEventRepo(conn).list_for_session(sid)
    assert ("streaming_stt", "reconnected") in {(e.stage, e.status) for e in events}


def test_poll_marks_degraded_when_stt_dies(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            offline_confirm_sec=45,
            min_recording_sec_before_offline_end=0,
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=False),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAApoll_stt",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAApoll_stt/live/x.flv"
    flv.parent.mkdir(parents=True)
    flv.write_bytes(b"x" * 8192)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="1", is_live=True, stream_flv_url="https://example.com/live.flv"
    )

    dead_stt = MagicMock()
    dead_stt.is_alive.return_value = False

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = dead_stt
    core._stream_urls[sid] = "https://example.com/live.flv"

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_finalize_recording") as mock_finalize,
    ):
        core.poll_active_recordings()

    mock_finalize.assert_not_called()
    assert sid in core._streaming_legacy_finalize
