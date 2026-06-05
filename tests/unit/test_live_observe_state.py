from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, DesktopEventRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_observe_live_state_does_not_start_recording(tmp_path, monkeypatch) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_observe",
        profile_url="https://www.douyin.com/user/sec_observe",
        platform="douyin",
        monitor_enabled=True,
    )
    creator = CreatorRepo(conn).get(cid)
    assert creator is not None

    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    adapter = MagicMock()
    adapter.get_live_room.return_value = live

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    monkeypatch.setattr(
        "media2text.core.live.recording.effective_auto_record",
        lambda *a, **k: True,
    )

    with patch.object(core, "_start_recording") as mock_start:
        with patch.object(core, "maybe_start_recording") as mock_maybe:
            info, err = core.observe_live_state(creator)

    mock_start.assert_not_called()
    mock_maybe.assert_not_called()
    assert err is None
    assert info is not None and info.is_live
    pending = DesktopEventRepo(conn).claim_pending(limit=5)
    assert len(pending) == 1
    assert pending[0].creator_id == cid
    conn.close()


def test_scan_and_start_calls_maybe_start_recording_when_auto_record(
    tmp_path, monkeypatch
) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_scan",
        profile_url="https://www.douyin.com/user/sec_scan",
        platform="douyin",
        monitor_enabled=True,
    )

    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    adapter = MagicMock()
    adapter.get_live_room.return_value = live

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    monkeypatch.setattr(
        "media2text.core.live.recording.effective_auto_record",
        lambda *a, **k: True,
    )

    with patch.object(
        core,
        "maybe_start_recording",
        return_value={"session_id": "s1", "temp_path": "/x.flv", "pid": 1},
    ) as mock_maybe:
        core.scan_and_start(creator_id=cid)

    mock_maybe.assert_called_once()
    conn.close()
