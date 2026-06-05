from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.download import download_pending
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def test_download_pending_respects_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAtest",
        profile_url="https://www.douyin.com/user/test",
        monitor_enabled=True,
    )
    for i in range(3):
        awemes.upsert_listed(
            creator_id=cid,
            item=AwemeItem(
                aweme_id=f"712345678901234567{i}",
                title=f"v{i}",
                create_time=1710000000 + i,
            ),
        )

    submitted: list[str] = []

    def fake_download_one(*, adapter, aweme_id, dest, session_file, download_url=None, **kwargs):
        submitted.append(aweme_id)
        return aweme_id, True, str(dest)

    with patch(
        "media2text.core.platform.douyin.download._download_one",
        side_effect=fake_download_one,
    ):
        result = download_pending(cfg, creator_id=cid, limit=1)

    assert result["downloaded"] == 1
    assert len(submitted) == 1
