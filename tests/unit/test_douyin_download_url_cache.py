from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.download import _download_one
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.platform.douyin.parse import extract_aweme_download_url
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def test_extract_aweme_download_url_prefers_highest_bit_rate_no_watermark() -> None:
    row = {
        "aweme_id": "1",
        "video": {
            "bit_rate": [
                {
                    "bit_rate": 800000,
                    "play_addr": {"url_list": ["https://example.com/low.mp4?watermark=1"]},
                },
                {
                    "bit_rate": 2500000,
                    "play_addr": {
                        "url_list": ["https://douyinvod.com/high.mp4?watermark=0"]
                    },
                },
            ],
            "play_addr": {"url_list": ["https://example.com/fallback.mp4"]},
        },
    }
    assert extract_aweme_download_url(row) == "https://douyinvod.com/high.mp4?watermark=0"


def test_download_one_uses_cached_url_without_detail_lookup(tmp_path) -> None:
    dest = tmp_path / "7123456789012345678.mp4"
    cached = "https://example.com/cached.mp4"

    with patch(
        "media2text.core.platform.douyin.download._stream_to_file",
        side_effect=lambda url, path: path.write_bytes(b"ok"),
    ) as stream_mock:
        aweme_id, ok, result = _download_one(
            adapter=object(),
            aweme_id="7123456789012345678",
            dest=dest,
            session_file=None,
            download_url=cached,
        )

    assert ok is True
    assert result == str(dest)
    stream_mock.assert_called_once_with(cached, dest)


def test_download_pending_passes_cached_url(tmp_path, monkeypatch) -> None:
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
    awemes.upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="7123456789012345678",
            title="v1",
            create_time=1710000000,
            download_url="https://example.com/cached.mp4",
        ),
    )

    seen: dict[str, str | None] = {}

    def fake_download_one(*, adapter, aweme_id, dest, session_file, download_url=None, **kwargs):
        seen[aweme_id] = download_url
        return aweme_id, True, str(dest)

    with patch(
        "media2text.core.platform.douyin.download._download_one",
        side_effect=fake_download_one,
    ):
        from media2text.core.platform.douyin.download import download_pending

        result = download_pending(cfg, creator_id=cid, limit=1)

    assert result["downloaded"] == 1
    assert seen["7123456789012345678"] == "https://example.com/cached.mp4"
