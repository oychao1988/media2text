from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _creator(workspace, platform: str = "douyin") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=f"sec_{platform}",
        profile_url=f"https://example.com/{platform}",
        platform=platform,
        monitor_enabled=True,
    )
    conn.close()
    return cid


def test_sync_profile(api_client, workspace) -> None:
    cid = _creator(workspace)
    with patch(
        "media2text.api.routes.creators.sync_creator_profile",
        return_value={"ok": True, "creator_id": cid},
    ):
        r = api_client.post(f"/api/creators/{cid}/sync-profile")
    assert r.status_code == 200


def test_sync_catalog(api_client, workspace) -> None:
    cid = _creator(workspace)
    with patch(
        "media2text.api.routes.creators.creator_svc.sync_creator_catalog",
        return_value={"ok": True},
    ):
        r = api_client.post(f"/api/creators/{cid}/sync")
    assert r.status_code == 200


def test_sync_catalog_enqueue_download(api_client, workspace) -> None:
    cid = _creator(workspace)
    with patch(
        "media2text.api.routes.creators.creator_svc.sync_creator_catalog",
        return_value={"ok": True},
    ):
        r = api_client.post(f"/api/creators/{cid}/sync?enqueue_download=true")
    assert r.status_code == 200
    body = r.json()
    assert body["download_queued"] is True
    assert body.get("download_task_id")


def test_enqueue_download(api_client, workspace) -> None:
    cid = _creator(workspace)
    r = api_client.post(f"/api/creators/{cid}/download")
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "queued"
    r2 = api_client.post(f"/api/creators/{cid}/download")
    assert r2.status_code == 409


def test_sync_dynamics_bilibili_only(api_client, workspace) -> None:
    douyin_id = _creator(workspace, "douyin")
    r = api_client.post(f"/api/creators/{douyin_id}/sync-dynamics")
    assert r.status_code == 400

    bili_id = _creator(workspace, "bilibili")
    with patch(
        "media2text.core.platform.bilibili.dynamic.sync_creator_dynamics",
        return_value={"ok": True},
    ):
        r = api_client.post(f"/api/creators/{bili_id}/sync-dynamics")
    assert r.status_code == 200
