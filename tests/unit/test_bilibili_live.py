import os
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.errors import AuthRequired, PlatformChanged
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.live import LiveWatcher
from media2text.core.platform.bilibili.parse import check_api_code
from media2text.core.platform.bilibili.resolver import resolve_mid
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PipelineEventRepo
from media2text.core.workspace import open_db


def test_resolve_mid_from_space_url() -> None:
    assert resolve_mid("https://space.bilibili.com/12345678") == "12345678"
    assert resolve_mid("https://space.bilibili.com/12345678/") == "12345678"


def test_resolve_mid_invalid_url() -> None:
    from media2text.core.errors import ParseFailed

    with pytest.raises(ParseFailed, match="not a bilibili"):
        resolve_mid("https://www.douyin.com/user/foo")


def test_bilibili_adapter_fixture_live() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
    info = adapter.get_live_room(sec_uid="12345")
    assert info.is_live is True
    assert info.room_id == "73182963"
    assert info.stream_flv_url == "https://example.com/bilibili-live.flv"


def test_bilibili_adapter_fixture_offline() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
    info = adapter.get_live_room(sec_uid="offline")
    assert info.is_live is False


def test_bilibili_adapter_no_session_raises_auth() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=False)
    with pytest.raises(AuthRequired):
        adapter.get_live_room(sec_uid="12345")


def test_bilibili_parse_platform_changed() -> None:
    import json

    payload = json.loads((FIXTURE_ROOT / "platform_changed.json").read_text())
    with pytest.raises(PlatformChanged):
        check_api_code(payload)


def test_bilibili_parse_auth_required() -> None:
    import json

    payload = json.loads((FIXTURE_ROOT / "auth_required.json").read_text())
    with pytest.raises(AuthRequired):
        check_api_code(payload)


def test_bilibili_live_run_once_starts_recording(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = repo.add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
        monitor_enabled=True,
    )
    core = watcher.core_for_conn(conn)

    mock_proc = MagicMock()
    mock_proc.pid = os.getpid()
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    with (
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
        patch.object(watcher, "_process_alive", return_value=True),
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4"),
    ):
        meta = core.start_recording_for_creator(cid)

    assert meta.get("session_id")
    active = sessions.get_active_for_creator(cid)
    assert active is not None
    assert active.status == "recording"


def test_bilibili_live_skips_douyin_creator(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    repo.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAAtest",
        platform="douyin",
        monitor_enabled=True,
    )
    conn.close()
    result = watcher.run_probe_observe()
    assert result["checked"] == 0
    assert result["started"] == 0


def test_bilibili_live_starts_streaming_stt_dual_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            remux_on_complete=False,
            streaming_stt=StreamingSttConfig(enabled=True),
        ),
    )
    watcher = LiveWatcher(cfg)
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
        monitor_enabled=True,
    )
    core = watcher.core_for_conn(conn)

    mock_proc = MagicMock()
    mock_proc.pid = os.getpid()
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    mock_stt = MagicMock()

    with (
        patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ),
        patch("media2text.core.live.recording.time.sleep"),
        patch.object(watcher, "_process_alive", return_value=True),
        patch("media2text.core.live.recording.stop_process"),
        patch(
            "media2text.core.live.recording.StreamingSttSession",
            return_value=mock_stt,
        ),
    ):
        meta = core.start_recording_for_creator(cid)

    assert meta.get("session_id")
    mock_stt.start.assert_called_once()
    session_id = meta["session_id"]
    assert session_id in core._stt_sessions
    events = PipelineEventRepo(conn).list_for_session(session_id)
    stages = {(e.stage, e.status) for e in events}
    assert ("streaming_stt", "started") in stages
