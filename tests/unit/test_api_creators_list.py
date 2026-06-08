import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed(workspace) -> tuple[str, str]:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    on_id = repo.add(
        sec_uid="sec_on",
        profile_url="https://www.douyin.com/user/sec_on",
        platform="douyin",
        monitor_enabled=True,
        display_name="Monitored",
    )
    off_id = repo.add(
        sec_uid="sec_off",
        profile_url="https://www.douyin.com/user/sec_off",
        platform="douyin",
        monitor_enabled=False,
        display_name="Hidden",
    )
    LiveSnapshotRepo(conn).upsert(on_id, is_live=True, room_id="r1", title="live")
    repo.update_profile(
        on_id,
        avatar_url="https://example.com/a.jpg",
        signature="hello world",
        follower_count=12345,
        profile_synced_at="2026-06-05T12:00:00+00:00",
    )
    conn.close()
    return on_id, off_id


def test_list_monitored_only(api_client, workspace) -> None:
    on_id, off_id = _seed(workspace)
    r = api_client.get("/api/creators")
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["creators"]}
    assert on_id in ids
    assert off_id not in ids
    item = next(c for c in r.json()["creators"] if c["id"] == on_id)
    assert item["status_light"] == "red"
    assert item["is_live"] is True
    assert item["avatar_url"] == "https://example.com/a.jpg"
    assert item["signature"] == "hello world"
    assert item["follower_count"] == 12345
    assert item["profile_synced_at"] == "2026-06-05T12:00:00+00:00"
    assert item["live_snapshot"]["is_live"] is True
    assert item["pipeline_phase"] == "live_unrecorded"


def test_list_all_query(api_client, workspace) -> None:
    on_id, off_id = _seed(workspace)
    r = api_client.get("/api/creators?all=1")
    ids = {c["id"] for c in r.json()["creators"]}
    assert on_id in ids
    assert off_id in ids
