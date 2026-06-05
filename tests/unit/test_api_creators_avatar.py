from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.workspace import open_db
from media2text.core.storage.repos import CreatorRepo

pytestmark = pytest.mark.desktop


def _seed_with_avatar(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="sec_avatar",
        profile_url="https://www.douyin.com/user/sec_avatar",
        platform="douyin",
        monitor_enabled=True,
        display_name="Avatar User",
    )
    repo.update_profile(
        cid,
        avatar_url="https://p3.douyinpic.com/aweme/avatar.jpg",
        profile_synced_at="2026-06-05T00:00:00+00:00",
    )
    conn.close()
    return cid


def test_avatar_proxy_returns_image(api_client, workspace) -> None:
    cid = _seed_with_avatar(workspace)
    fake_body = b"\xff\xd8\xff fake jpeg"
    with patch(
        "media2text.api.routes.creators.creator_avatar_svc.fetch_creator_avatar",
        return_value=(fake_body, "image/jpeg"),
    ):
        r = api_client.get(f"/api/creators/{cid}/avatar")
    assert r.status_code == 200
    assert r.content == fake_body
    assert r.headers["content-type"].startswith("image/jpeg")


def test_avatar_not_found_without_url(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_no_avatar",
        profile_url="https://www.douyin.com/user/sec_no_avatar",
        platform="douyin",
    )
    conn.close()
    r = api_client.get(f"/api/creators/{cid}/avatar")
    assert r.status_code == 404
