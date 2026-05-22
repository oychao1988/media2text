from media2text.core.config import AppConfig
from media2text.core.platform.profile import sync_creator_profile
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_sync_creator_profile_bilibili_fixture(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creator_id = repo.add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
    )

    result = sync_creator_profile(cfg, creator_id)

    assert result["ok"] is True
    assert result["platform"] == "bilibili"
    row = repo.get(creator_id)
    assert row is not None
    assert row.display_name == "fixture_up"
    assert row.avatar_url == "https://example.com/face.jpg"
    assert row.signature == "hello"
    assert row.follower_count == 1000
    assert row.profile_synced_at


def test_sync_creator_profile_douyin_fixture(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creator_id = repo.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAAtest",
        platform="douyin",
    )

    result = sync_creator_profile(cfg, creator_id)

    assert result["ok"] is True
    assert result["platform"] == "douyin"
    row = repo.get(creator_id)
    assert row is not None
    assert row.display_name == "测试博主"
    assert row.unique_id == "test_creator"
    assert row.profile_synced_at
