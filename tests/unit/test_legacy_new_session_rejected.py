from unittest.mock import MagicMock

import pytest

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.errors import RecordingError
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_legacy_new_session_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(pipeline_mode="legacy"),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAlegacyReject",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    live_info = LiveRoomInfo(room_id="1", is_live=True, stream_flv_url="https://x/flv")

    with pytest.raises(RecordingError, match="pipeline_mode=streaming"):
        core._start_recording(cid, "MS4wLjABAAAAlegacyReject", "1", live_info)

    assert LiveSessionRepo(conn).list_active() == []


def test_snapshot_pipeline_mode_still_legacy_for_existing_finalize(tmp_path) -> None:
    cfg = AppConfig(live=LiveConfig(pipeline_mode="legacy"))
    assert cfg.live.effective_pipeline_mode() == "legacy"
    assert cfg.live.snapshot_pipeline_mode() == "legacy"
