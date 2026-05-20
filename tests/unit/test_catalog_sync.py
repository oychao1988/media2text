from media2text.core.config import AppConfig
from media2text.core.platform.douyin.catalog import sync_creator
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def test_sync_creator_with_fixtures(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/test",
        monitor_enabled=False,
    )
    result = sync_creator(cfg, cid)
    assert result["ok"] is True
    assert result["new_count"] == 2
    awemes = AwemeRepo(conn).list_for_creator(cid)
    assert len(awemes) == 2
