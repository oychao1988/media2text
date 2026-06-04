from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db
from media2text.api.services import live_snapshot as live_snapshot_svc

pytestmark = pytest.mark.desktop


def _seed(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_refresh",
        profile_url="https://www.douyin.com/user/sec_refresh",
        platform="douyin",
    )
    conn.close()
    return cid


def test_live_refresh_upserts_snapshot(api_client, workspace) -> None:
    live_snapshot_svc.clear_refresh_rate_limit_for_tests()
    cid = _seed(workspace)
    live = LiveRoomInfo(room_id="99", is_live=True, title="on air")
    with patch(
        "media2text.api.services.live_snapshot.get_adapter"
    ) as mock_adapter:
        mock_adapter.return_value.get_live_room.return_value = live
        r = api_client.post(f"/api/creators/{cid}/live/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["live_snapshot"]["is_live"] is True
    assert body["live_snapshot"]["room_id"] == "99"

    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    snap = LiveSnapshotRepo(conn).get(cid)
    conn.close()
    assert snap is not None
    assert snap.is_live == 1
    assert snap.room_id == "99"


def test_live_refresh_rate_limit_429(api_client, workspace) -> None:
    live_snapshot_svc.clear_refresh_rate_limit_for_tests()
    cid = _seed(workspace)
    live = LiveRoomInfo(room_id="99", is_live=False)
    with patch(
        "media2text.api.services.live_snapshot.get_adapter"
    ) as mock_adapter:
        mock_adapter.return_value.get_live_room.return_value = live
        r1 = api_client.post(f"/api/creators/{cid}/live/refresh")
        r2 = api_client.post(f"/api/creators/{cid}/live/refresh")
    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r2.json()["detail"]["rate_limited"] is True
