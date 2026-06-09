from unittest.mock import MagicMock, patch
import json

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.notify.events import EventKind
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)


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
    from media2text.core.live.task_reconciler import reconcile_live
    from media2text.core.storage.repos import MonitorTaskRepo

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
        patch.object(core, "_recording_still_live", return_value=True),
    ):
        core.poll_active_recordings()
        reconcile_live(cfg, conn)

    row = sessions.get(sid)
    assert row is not None
    assert row.obs_ffmpeg_alive == 0
    assert row.obs_still_live == 1
    assert MonitorTaskRepo(conn).has_active_dedupe(f"reconnect_rec:{sid}")


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
        patch("media2text.core.manifest.refresh_manifest"),
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


def test_start_recording_stream_resolve_event(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAresolve",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    adapter = MagicMock()
    adapter.resolve_stream_url.return_value = "https://example.com/live.flv"
    live_info = LiveRoomInfo(
        room_id="731829",
        is_live=True,
        stream_flv_url=None,
        platform_live_started_at="2026-06-03T10:00:00+00:00",
    )
    mock_proc = MagicMock()
    mock_proc.pid = 5555
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
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
    ):
        meta = core._start_recording(cid, "MS4wLjABAAAAresolve", "731829", live_info)

    row = LiveSessionRepo(conn).get(meta["session_id"])
    assert row is not None
    assert row.platform_live_started_at == "2026-06-03T10:00:00+00:00"
    events = PipelineEventRepo(conn).list_for_session(meta["session_id"])
    stages = [e.stage for e in events]
    assert "detected_live" in stages
    assert "stream_resolve" in stages
    assert "recording" in stages


def _streaming_core(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstream",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAstream/live/part.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="88",
        temp_path=str(flv),
        ffmpeg_pid=None,
        pipeline_mode="streaming",
    )
    adapter = MagicMock()
    adapter.resolve_stream_url.return_value = "https://example.com/live.flv"
    notify = MagicMock()
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=notify,
    )
    live_info = LiveRoomInfo(
        room_id="88",
        is_live=True,
        stream_flv_url="https://example.com/live.flv",
    )
    mock_proc = MagicMock()
    mock_proc.pid = 7777
    mock_proc.poll.return_value = None
    mock_proc.stderr = None
    return core, conn, sid, flv, live_info, notify, mock_proc, cid


def test_live_started_emitted_before_streaming_stt_blocks(
    tmp_path, monkeypatch
) -> None:
    core, _conn, sid, flv, live_info, notify, mock_proc, cid = _streaming_core(
        tmp_path, monkeypatch
    )
    call_order: list[str] = []

    mock_stt = MagicMock()

    def _stt_start() -> None:
        call_order.append("stt_start")
        assert "live_started" in call_order

    mock_stt.start.side_effect = _stt_start

    def _track_emit(event) -> None:
        if event.kind == EventKind.LIVE_STARTED:
            call_order.append("live_started")

    notify.emit.side_effect = _track_emit

    with (
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
        patch.object(core, "_build_streaming_stt_session", return_value=mock_stt),
    ):
        core._start_recording_after_session(
            sid,
            creator_id=cid,
            sec_uid="MS4wLjABAAAAstream",
            room_id="88",
            live_info=live_info,
            temp_path=flv,
        )

    assert call_order.index("live_started") < call_order.index("stt_start")
    live_started_calls = [
        c
        for c in notify.emit.call_args_list
        if c[0][0].kind == EventKind.LIVE_STARTED
    ]
    assert len(live_started_calls) == 1
    evt = live_started_calls[0][0][0]
    assert evt.creator_id == cid
    assert evt.session_id == sid


def test_streaming_stt_start_fail_keeps_recording(tmp_path, monkeypatch) -> None:
    core, conn, sid, flv, live_info, notify, mock_proc, cid = _streaming_core(
        tmp_path, monkeypatch
    )
    mock_stt = MagicMock()
    mock_stt.start.side_effect = RuntimeError("deepgram unavailable")

    with (
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
        patch(
            "media2text.core.live.recording.stop_process",
        ) as mock_stop,
        patch.object(core, "_build_streaming_stt_session", return_value=mock_stt),
    ):
        core._start_recording_after_session(
            sid,
            creator_id=cid,
            sec_uid="MS4wLjABAAAAstream",
            room_id="88",
            live_info=live_info,
            temp_path=flv,
        )

    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.status == "recording"
    mock_stop.assert_not_called()
    assert sid in core._processes
    failed_kinds = [
        c[0][0].kind for c in notify.emit.call_args_list
    ]
    assert EventKind.LIVE_START_FAILED not in failed_kinds
    assert EventKind.LIVE_STARTED in failed_kinds
    events = PipelineEventRepo(conn).list_for_session(sid)
    degraded = [
        e
        for e in events
        if e.stage == "streaming_stt" and e.status == "degraded"
    ]
    assert len(degraded) == 1
    detail = json.loads(degraded[0].detail_json or "{}")
    assert detail.get("reason") == "stt_start_failed"


def test_stall_recovery_reconnects_stt_without_killing_ffmpeg(tmp_path, monkeypatch) -> None:
    """Stale partial + dead STT + live ffmpeg → STT-only reconnect, not full segment reconnect."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAASttstall",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAASttstall/live/20260609T124929Z"
    session_dir.mkdir(parents=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    anchor = session_dir / "20260609T124929Z.flv"
    anchor.write_bytes(b"\x00")
    partial = session_dir / "master.transcript.partial.json"
    partial.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 120.0, "text": "hello"}],
                "text": "hello",
            }
        ),
        encoding="utf-8",
    )
    old = partial.stat().st_mtime
    import os

    os.utime(partial, (old - 200, old - 200))

    sessions = LiveSessionRepo(conn)
    sid = sessions.create(
        creator_id=cid,
        room_id="room1",
        temp_path=str(master),
        ffmpeg_pid=9999,
        pipeline_mode="streaming",
    )
    conn.execute(
        "UPDATE live_sessions SET session_dir = ?, reconnect_attempts = 0 WHERE id = ?",
        (str(session_dir), sid),
    )
    conn.commit()

    adapter = MagicMock()
    row = sessions.get(sid)
    creator = CreatorRepo(conn).get(cid)
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={sid: MagicMock()},
        notify=MagicMock(),
    )
    core._streaming_transcript_anchor[sid] = anchor

    with (
        patch.object(core, "_reconnect_segment") as mock_segment,
        patch.object(core, "_handle_stt_disconnect") as mock_stt,
    ):
        core._maybe_recover_stalled_stream(
            row,
            creator,
            ffmpeg_alive=True,
            stt_alive=False,
        )

    mock_stt.assert_called_once()
    mock_segment.assert_not_called()
    conn.close()
