import os
import sys
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, TranscribeConfig
from media2text.core.platform.douyin.live import LiveWatcher
from media2text.core.storage.repos import CreatorRepo
from media2text.core.transcribe.base import TranscriptResult


def test_run_once_starts_recording_for_live_creator(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    conn = watcher._conn
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAAtest",
        monitor_enabled=True,
    )

    mock_proc = MagicMock()
    mock_proc.pid = os.getpid()
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    with (
        patch(
            "media2text.core.platform.douyin.live.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.platform.douyin.live.time.sleep"),
        patch.object(watcher, "_process_alive", return_value=True),
        patch("media2text.core.platform.douyin.live.stop_process"),
        patch("media2text.core.platform.douyin.live.remux_to_mp4"),
    ):
        result = watcher.run_once(creator_id=cid)

    assert len(result["started"]) == 1
    assert result["started"][0]["pid"] == os.getpid()
    active = watcher._sessions.get_active_for_creator(cid)
    assert active is not None
    assert active.status == "recording"


def test_get_active_for_creator_clears_dead_pid(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    conn = watcher._conn
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAdead",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = watcher._sessions.create(
        creator_id=cid,
        room_id="123",
        temp_path=str(tmp_path / "x.flv"),
        ffmpeg_pid=999999,
    )
    active = watcher._sessions.get_active_for_creator(cid)
    assert active is None
    row = conn.execute("SELECT status, error FROM live_sessions WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "stale_recording"


def test_poll_skips_fresh_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    repo = CreatorRepo(watcher._conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAskip",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = watcher._sessions.create(
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
    repo = CreatorRepo(watcher._conn)
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
    sid = watcher._sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )

    with (
        patch("media2text.core.platform.douyin.live.stop_process"),
        patch("media2text.core.platform.douyin.live.remux_to_mp4") as mock_remux,
        patch("media2text.core.platform.douyin.live.refresh_manifest") as mock_refresh,
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
        watcher._conn,
        sec_uid=sec_uid,
        workspace=cfg.ensure_workspace(),
    )


def test_finalize_transcribe_on_complete(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    watcher = LiveWatcher(cfg)
    repo = CreatorRepo(watcher._conn)
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
    sid = watcher._sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    fake_whisper = MagicMock()
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper)

    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = TranscriptResult(
        text="hello",
        segments=[],
        engine="whisper",
        model="tiny",
    )

    with (
        patch("media2text.core.platform.douyin.live.stop_process"),
        patch("media2text.core.platform.douyin.live.remux_to_mp4") as mock_remux,
        patch("media2text.core.platform.douyin.live.refresh_manifest") as mock_refresh,
        patch("media2text.core.platform.douyin.live.WhisperBackend", return_value=mock_backend),
        patch(
            "media2text.core.platform.douyin.live.write_transcript_outputs",
            return_value=(flv.with_suffix(".transcript.json"), flv.with_suffix(".transcript.md")),
        ),
        patch.object(watcher, "_process_alive", return_value=False),
    ):
        def _fake_remux(**_kwargs):
            _kwargs["dst"].write_bytes(b"\x00\x00\x00\x18ftyp")

        mock_remux.side_effect = _fake_remux
        meta = watcher._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    assert meta.get("transcribed") is True
    mock_backend.transcribe.assert_called_once()
    assert mock_refresh.call_count == 2


def test_finalize_transcribe_skipped_without_extra(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    watcher = LiveWatcher(cfg)
    repo = CreatorRepo(watcher._conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAskip",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data" / "creators" / "MS4wLjABAAAAskip" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260520T140000Z.flv"
    flv.write_bytes(b"x" * 64)
    sid = watcher._sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=1,
    )
    monkeypatch.delitem(sys.modules, "faster_whisper", raising=False)

    with (
        patch("media2text.core.platform.douyin.live.stop_process"),
        patch("media2text.core.platform.douyin.live.remux_to_mp4") as mock_remux,
        patch("media2text.core.platform.douyin.live.refresh_manifest"),
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
    assert meta.get("transcribe_skipped") is True
