from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_creator_remove_delete_media(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    sec_uid = "MS4wLjABAAAAdelete"
    cid = repo.add(
        sec_uid=sec_uid,
        profile_url="https://www.douyin.com/user/delete",
        monitor_enabled=False,
    )
    media_dir = ws / "creators" / sec_uid
    media_dir.mkdir(parents=True)
    (media_dir / "marker.txt").write_text("x")

    assert repo.remove(cid) is True
    assert not repo.get(cid)
    assert media_dir.is_dir()

    import shutil

    shutil.rmtree(media_dir)
    assert not media_dir.exists()
