from media2text.core.config import AppConfig
from media2text.core.platform.douyin.catalog import sync_creator
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_sync_creator_platform_changed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAchanged",
        profile_url="https://www.douyin.com/user/changed",
        monitor_enabled=False,
    )

    from media2text.core.platform.douyin import catalog as catalog_mod

    class BrokenAdapter:
        def list_awemes(self, **kwargs):
            from media2text.core.errors import PlatformChanged

            raise PlatformChanged("test")

    monkeypatch.setattr(catalog_mod, "build_adapter", lambda _cfg: BrokenAdapter())
    result = sync_creator(cfg, cid)
    assert result["ok"] is False
    assert result["platform_changed"] is True
    assert result["auth_required"] is False
