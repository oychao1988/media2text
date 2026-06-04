from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_scan_and_start_upserts_snapshot(tmp_path, monkeypatch) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_snap",
        profile_url="https://www.douyin.com/user/sec_snap",
        platform="douyin",
        monitor_enabled=True,
    )
    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    adapter = type("A", (), {})()
    adapter.get_live_room = lambda *, sec_uid: live  # noqa: ARG005

    notify = type("N", (), {"emit": lambda *a, **k: None})()
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=notify,
    )
    monkeypatch.setattr(
        "media2text.core.live.recording.effective_auto_record",
        lambda *a, **k: False,
    )
    with patch.object(core, "_start_recording") as mock_start:
        core.scan_and_start()
    mock_start.assert_not_called()
    snap = LiveSnapshotRepo(conn).get(cid)
    conn.close()
    assert snap is not None
    assert snap.is_live == 1
    assert snap.room_id == "r1"
