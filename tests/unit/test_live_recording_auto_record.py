from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo


def test_scan_skips_start_when_auto_record_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.model_validate(
        {"workspace": str(tmp_path / "data"), "live": {"auto_record": False}}
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAauto",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )

    adapter = MagicMock()
    live = LiveRoomInfo(
        room_id="123", is_live=True, stream_flv_url="https://example.com/x.flv"
    )
    adapter.get_live_room.return_value = live

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )

    with patch.object(core, "_start_recording") as mock_start:
        started, _, errors, _, _ = core.scan_and_start(creator_id=cid)

    mock_start.assert_not_called()
    assert started == []
    assert errors == []
