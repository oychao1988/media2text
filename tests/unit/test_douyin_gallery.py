from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.adapter import FIXTURE_ROOT, DouyinAdapterV1
from media2text.core.platform.douyin.download import _download_one
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.platform.douyin.parse import (
    detect_aweme_media_type,
    extract_gallery_image_urls,
    parse_aweme_item,
)
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def test_detect_gallery_from_aweme_type_and_images() -> None:
    row = {
        "aweme_id": "7578146088285768692",
        "aweme_type": 68,
        "images": [
            {"display_image": {"url_list": ["https://example.com/1.jpeg"]}},
        ],
    }
    assert detect_aweme_media_type(row) == "gallery"
    item = parse_aweme_item(row)
    assert item.media_type == "gallery"
    assert item.media_urls == ["https://example.com/1.jpeg"]


def test_note_with_video_stays_video() -> None:
    row = {
        "aweme_id": "1",
        "aweme_type": 68,
        "video": {
            "play_addr": {"url_list": ["https://example.com/note-video.mp4"]},
        },
    }
    assert detect_aweme_media_type(row) == "video"
    assert extract_gallery_image_urls(row) == []


def test_adapter_resolve_gallery_urls_fixture() -> None:
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)
    urls = adapter.resolve_gallery_urls(aweme_id="7578146088285768692")
    assert urls == [
        "https://example.com/gallery-detail.jpeg",
        "https://example.com/gallery-detail-2.webp",
    ]


def test_download_gallery_writes_image_files(tmp_path) -> None:
    dest_dir = tmp_path / "7578146088285768692"
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)

    with patch(
        "media2text.core.platform.douyin.download._stream_to_file",
        side_effect=lambda url, path: path.write_bytes(b"img"),
    ) as stream_mock:
        aweme_id, ok, result = _download_one(
            adapter=adapter,
            aweme_id="7578146088285768692",
            dest=dest_dir,
            session_file=None,
            media_type="gallery",
            media_urls=["https://example.com/a.jpeg", "https://example.com/b.webp"],
        )

    assert ok is True
    assert result == str(dest_dir)
    assert stream_mock.call_count == 2


def test_download_pending_gallery_uses_images_dir(tmp_path, monkeypatch) -> None:
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
            aweme_id="7578146088285768692",
            title="gallery",
            create_time=1710002000,
            media_type="gallery",
            media_urls=["https://example.com/a.jpeg"],
        ),
    )

    seen: dict[str, str] = {}

    def fake_download_one(*, adapter, aweme_id, dest, session_file, download_url=None, **kwargs):
        seen["dest"] = str(dest)
        seen["media_type"] = kwargs.get("media_type", "video")
        return aweme_id, True, str(dest)

    with patch(
        "media2text.core.platform.douyin.download._download_one",
        side_effect=fake_download_one,
    ):
        from media2text.core.platform.douyin.download import download_pending

        result = download_pending(cfg, creator_id=cid, limit=1)

    assert result["downloaded"] == 1
    assert seen["media_type"] == "gallery"
    assert seen["dest"].endswith("/images/7578146088285768692")
