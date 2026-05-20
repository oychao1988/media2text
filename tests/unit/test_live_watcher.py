import os
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.live import LiveWatcher
from media2text.core.storage.repos import CreatorRepo


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
