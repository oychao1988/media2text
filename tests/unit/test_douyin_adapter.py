from media2text.core.platform.douyin.adapter import FIXTURE_ROOT, DouyinAdapterV1


def test_get_live_room_offline_fixture() -> None:
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)
    info = adapter.get_live_room(sec_uid="offline")
    assert info.is_live is False
    assert info.room_id is None


def test_get_live_room_with_stream_fixture() -> None:
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)
    info = adapter.get_live_room(sec_uid="MS4wLjABAAAAtest")
    assert info.is_live is True
    assert info.room_id == "7318296342189919011"
    assert info.stream_flv_url == "https://example.com/live/stream.flv"


def test_list_awemes_fixture() -> None:
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)
    items, cursor, has_more = adapter.list_awemes(sec_uid="x")
    assert len(items) == 3
    assert items[0].aweme_id == "7123456789012345678"
    assert items[0].download_url == "https://example.com/video-one.mp4"
    assert items[1].download_url == "https://douyinvod.com/high.mp4?watermark=0"
    assert items[2].media_type == "gallery"
    assert items[2].media_urls == ["https://example.com/gallery-1.jpeg?watermark=0"]
    assert has_more is False


def test_resolve_download_url_fixture() -> None:
    adapter = DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)
    url = adapter.resolve_download_url(aweme_id="7123456789012345678")
    assert url == "https://example.com/video.mp4"
