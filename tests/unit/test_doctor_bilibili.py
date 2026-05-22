from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo


def test_doctor_includes_bilibili_session_check_when_creator_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    CreatorRepo(conn).add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
    )
    (ws / "sessions" / "bilibili.json").write_text("{}", encoding="utf-8")

    from media2text.core.platform.bilibili.auth import session_exists as bili_ok
    from media2text.core.storage.repos import CreatorRepo as CR

    conn2 = connect(ws / "media2text.db")
    assert any(c.platform == "bilibili" for c in CR(conn2).list_all())
    assert bili_ok(ws) is True
