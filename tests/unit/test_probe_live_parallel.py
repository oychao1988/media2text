from unittest.mock import MagicMock

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_probe_live_parallel_uses_per_thread_connections(tmp_path, monkeypatch) -> None:
    """DL-1: parallel probe persists via serial short connections (not one conn per worker)."""
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creators = []
    for i in range(4):
        cid = repo.add(
            sec_uid=f"sec_parallel_{i}",
            profile_url=f"https://www.douyin.com/user/sec_parallel_{i}",
            platform="douyin",
            monitor_enabled=True,
        )
        creators.append(repo.get(cid))
    conn.close()

    live = LiveRoomInfo(room_id="r1", is_live=False)
    adapter = MagicMock()
    adapter.get_live_room.return_value = live

    core = LiveRecordingCore(
        cfg,
        conn=open_db(cfg),
        adapter=adapter,
        platform="douyin",
        notify=MagicMock(),
    )

    errors, auth_required, platform_changed = core.probe_live()

    assert errors == []
    assert auth_required is False
    assert platform_changed is False

    verify = open_db(cfg)
    try:
        for creator in creators:
            assert creator is not None
            snap = LiveSnapshotRepo(verify).get(creator.id)
            assert snap is not None
            assert snap.is_live == 0
    finally:
        verify.close()
