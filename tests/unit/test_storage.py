from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo


def test_creator_roundtrip(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    repo = CreatorRepo(conn)
    cid = repo.add(sec_uid="sec123", profile_url="https://www.douyin.com/user/x", watch_live=True)
    row = repo.get(cid)
    assert row is not None
    assert row.sec_uid == "sec123"
    assert row.watch_live == 1
