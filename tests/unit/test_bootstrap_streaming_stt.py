from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.task_reconciler import bootstrap_streaming_stt
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def test_bootstrap_streaming_stt_reconnects_active_session(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAboot",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.m3u8"),
        ffmpeg_pid=99999,
        pipeline_mode="streaming",
    )

    watcher = MonitorWatcher(cfg)
    mock_core = MagicMock()
    mock_core._stt_sessions = {}
    mock_core.run_reconnect_streaming_stt.return_value = {
        "session_id": sid,
        "stt_reconnect_attempted": True,
    }

    with (
        patch.object(watcher, "core_for_platform", return_value=mock_core),
        patch(
            "media2text.core.live.task_reconciler._pid_alive",
            return_value=True,
        ),
    ):
        recovered = bootstrap_streaming_stt(cfg, watcher)

    assert recovered == 1
    mock_core.run_reconnect_streaming_stt.assert_called_once_with(sid)


def test_bootstrap_skips_when_stt_already_alive(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAboot2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="2",
        temp_path=str(tmp_path / "live2.m3u8"),
        ffmpeg_pid=88888,
        pipeline_mode="streaming",
    )

    watcher = MonitorWatcher(cfg)
    alive_stt = MagicMock()
    alive_stt.is_alive.return_value = True
    mock_core = MagicMock()
    mock_core._stt_sessions = {sid: alive_stt}

    with (
        patch.object(watcher, "core_for_platform", return_value=mock_core),
        patch(
            "media2text.core.live.task_reconciler._pid_alive",
            return_value=True,
        ),
    ):
        recovered = bootstrap_streaming_stt(cfg, watcher)

    assert recovered == 0
    mock_core.run_reconnect_streaming_stt.assert_not_called()
