from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _add_creator(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_crud",
        profile_url="https://www.douyin.com/user/sec_crud",
        platform="douyin",
        monitor_enabled=True,
    )
    conn.close()
    return cid


def test_get_creator_detail(api_client, workspace) -> None:
    cid = _add_creator(workspace)
    r = api_client.get(f"/api/creators/{cid}")
    assert r.status_code == 200
    body = r.json()["creator"]
    assert body["id"] == cid
    assert "auto_record_override" in body
    assert "live_snapshot" in body


def test_patch_monitor_and_override(api_client, workspace) -> None:
    cid = _add_creator(workspace)
    r = api_client.patch(
        f"/api/creators/{cid}",
        json={"monitorEnabled": False, "autoRecordOverride": "on"},
    )
    assert r.status_code == 200
    assert r.json()["auto_record_override"] == "on"
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    row = CreatorRepo(open_db(cfg)).get(cid)
    assert row is not None
    assert row.monitor_enabled == 0
    assert row.auto_record_override == "on"


def test_patch_content_sync(api_client, workspace) -> None:
    cid = _add_creator(workspace)
    r = api_client.patch(
        f"/api/creators/{cid}",
        json={"contentSyncEnabled": True},
    )
    assert r.status_code == 200
    assert r.json()["content_sync_enabled"] is True
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    repo = CreatorRepo(open_db(cfg))
    row = repo.get(cid)
    assert row is not None
    assert row.content_sync_enabled == 1
    r2 = api_client.patch(
        f"/api/creators/{cid}",
        json={"contentSyncEnabled": False},
    )
    assert r2.status_code == 200
    row2 = repo.get(cid)
    assert row2 is not None
    assert row2.content_sync_enabled == 0
    assert row2.vod_due_at is None


def test_patch_invalid_override(api_client, workspace) -> None:
    cid = _add_creator(workspace)
    r = api_client.patch(
        f"/api/creators/{cid}",
        json={"autoRecordOverride": "maybe"},
    )
    assert r.status_code == 400


def test_post_creator_mocked(api_client) -> None:
    with patch(
        "media2text.api.routes.creators.creator_svc.add_creator_from_url",
        return_value={
            "ok": True,
            "creator_id": "new-id",
            "sec_uid": "s",
            "platform": "douyin",
            "monitor_enabled": False,
        },
    ):
        r = api_client.post(
            "/api/creators",
            json={"url": "https://www.douyin.com/user/x", "platform": "douyin"},
        )
    assert r.status_code == 200
    assert r.json()["creator_id"] == "new-id"


def test_delete_creator(api_client, workspace) -> None:
    cid = _add_creator(workspace)
    r = api_client.delete(f"/api/creators/{cid}")
    assert r.status_code == 200
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    assert CreatorRepo(open_db(cfg)).get(cid) is None
