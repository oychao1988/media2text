from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
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
