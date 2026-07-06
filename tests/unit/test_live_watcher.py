from unittest.mock import ANY, MagicMock, patch

import pytest

from media2text.core.config import AppConfig, LiveConfig, TranscribeConfig
from media2text.core.platform.douyin.live import LiveWatcher
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db


@pytest.fixture(autouse=True)
def _reset_db_write_gateway() -> None:
    yield
    import media2text.core.storage.write_gateway as wg_mod

    shutdown_write_gateway()
    wg_mod._gateway = None


def test_run_probe_observe_only_does_not_start_recording(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    ensure_write_gateway_started(cfg)
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAAtest",
        monitor_enabled=True,
    )
    conn.close()

    live = LiveRoomInfo(
        room_id="123",
        is_live=True,
        stream_flv_url="https://example.com/live.flv",
    )
    with patch.object(watcher._adapter, "get_live_room", return_value=live):
        result = watcher.run_probe_observe(creator_id=cid)

    assert result.get("probe") is True
    assert result.get("started") == 0
    conn = open_db(cfg)
    try:
        assert LiveSessionRepo(conn).get_active_for_creator(cid) is None
    finally:
        conn.close()


def test_poll_observe_when_ffmpeg_dead_skips_stale(tmp_path, monkeypatch) -> None:
    """Dead ffmpeg: poll writes obs; stale must not mark failed (Reconciler owns exit)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(min_recording_sec_before_offline_end=0),
    )
    ensure_write_gateway_started(cfg)
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    sec_uid = "MS4wLjABAAAAstalefix"
    cid = repo.add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data" / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260602T120000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=999999,
    )
    conn.close()

    offline = LiveRoomInfo(room_id="99", is_live=False, stream_flv_url=None)
    with (
        patch.object(watcher._adapter, "get_live_room", return_value=offline),
        patch(
            "media2text.core.live.recording.LiveRecordingCore._process_alive",
            return_value=False,
        ),
    ):
        watcher.run_poll_active()
        watcher.run_probe_observe(creator_id=cid)

    conn = open_db(cfg)
    try:
        row = conn.execute(
            "SELECT status, obs_ffmpeg_alive, error FROM live_sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row["status"] == "recording"
        assert row["obs_ffmpeg_alive"] == 0
        assert row["error"] is None
    finally:
        conn.close()


def test_get_active_for_creator_keeps_dead_pid_for_poll(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAdead",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = sessions.create(
        creator_id=cid,
        room_id="123",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=999999,
    )
    active = sessions.get_active_for_creator(cid)
    assert active is not None
    assert active.id == sid
    row = conn.execute("SELECT status, error FROM live_sessions WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "recording"
    assert row["error"] is None


def test_poll_skips_fresh_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
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

    with (
        patch.object(watcher, "_process_alive", return_value=True),
        patch.object(watcher._adapter, "get_live_room") as mock_live,
        patch.object(watcher, "_finalize_recording") as mock_finalize,
    ):
        mock_live.return_value = MagicMock(is_live=False)
        watcher._poll_active_recordings(skip_session_ids={sid})

    mock_finalize.assert_not_called()


def test_finalize_refresh_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    sec_uid = "MS4wLjABAAAAfinalize"
    cid = repo.add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data" / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260520T120000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
        pipeline_mode="legacy",
    )

    with (
        patch("media2text.core.live.session_finalize.stop_process"),
        patch("media2text.core.live.session_finalize.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.state_writer.refresh_manifest") as mock_refresh,
        patch.object(watcher._notify, "emit"),
        patch.object(watcher, "_process_alive", return_value=False),
    ):
        def _fake_remux(**_kwargs):
            dst = _kwargs["dst"]
            dst.write_bytes(b"\x00\x00\x00\x18ftyp")

        mock_remux.side_effect = _fake_remux
        meta = watcher._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    assert meta["session_id"] == sid
    mp4 = flv.with_suffix(".mp4")
    assert meta["path"] == str(mp4)
    assert mock_refresh.call_count == 1
    mock_refresh.assert_called_with(
        ANY,
        sec_uid=sec_uid,
        workspace=cfg.ensure_workspace(),
        platform="douyin",
    )


def test_finalize_transcribe_on_complete(tmp_path, monkeypatch) -> None:
    from media2text.core.storage.repos import PostProcessJobRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    jobs = PostProcessJobRepo(conn)
    sec_uid = "MS4wLjABAAAAtx"
    cid = repo.add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data" / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260520T130000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
        pipeline_mode="legacy",
    )

    with (
        patch("media2text.core.live.session_finalize.stop_process"),
        patch("media2text.core.live.session_finalize.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.state_writer.refresh_manifest"),
        patch.object(watcher._notify, "emit"),
        patch.object(watcher, "_process_alive", return_value=False),
    ):
        def _fake_remux(**_kwargs):
            _kwargs["dst"].write_bytes(b"\x00\x00\x00\x18ftyp")

        mock_remux.side_effect = _fake_remux
        meta = watcher._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    pending = jobs.list_pending(limit=5)
    assert len(pending) == 1
    assert pending[0].session_id == sid


def test_finalize_transcribe_skipped_without_extra(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAskip",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data" / "creators" / "MS4wLjABAAAAskip" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260520T140000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=1,
        pipeline_mode="legacy",
    )

    with (
        patch("media2text.core.live.session_finalize.stop_process"),
        patch("media2text.core.live.session_finalize.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.state_writer.refresh_manifest"),
        patch.object(watcher, "_process_alive", return_value=False),
    ):
        def _fake_remux(**_kwargs):
            _kwargs["dst"].write_bytes(b"\x00\x00\x00\x18ftyp")

        mock_remux.side_effect = _fake_remux

        def _import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("no transcribe extra")
            return orig_import(name, *args, **kwargs)

        orig_import = __import__
        monkeypatch.setattr("builtins.__import__", _import)
        meta = watcher._finalize_recording(sid, str(flv), 1)

    assert meta is not None
    assert "job_id" in meta
