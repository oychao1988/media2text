import pytest

from media2text.core.errors import PlatformChanged
from media2text.core.platform.douyin.parse import parse_aweme_detail_url, parse_aweme_post_list


def test_parse_aweme_post_list_raises_platform_changed_on_missing_list() -> None:
    with pytest.raises(PlatformChanged, match="status_code"):
        parse_aweme_post_list({"status_code": 10008, "status_msg": "invalid parameter"})


def test_parse_aweme_post_list_ok_with_fixture_shape() -> None:
    payload = {
        "aweme_list": [{"aweme_id": "1", "desc": "a"}],
        "max_cursor": "0",
        "has_more": 0,
    }
    items, cursor, has_more = parse_aweme_post_list(payload)
    assert len(items) == 1
    assert cursor == "0"
    assert has_more is False


def test_parse_aweme_detail_raises_platform_changed_on_status() -> None:
    with pytest.raises(PlatformChanged, match="status_code"):
        parse_aweme_detail_url({"status_code": 5, "status_msg": "gone"})
