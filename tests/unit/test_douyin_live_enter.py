import pytest

from media2text.core.errors import ParseFailed
from media2text.core.platform.douyin.live_enter import (
    flv_from_room_dict,
    room_from_enter_payload,
)


def test_room_from_enter_payload_list_shape() -> None:
    payload = {
        "data": {
            "data": [
                {
                    "id_str": "731829",
                    "title": "测试直播",
                    "status": 2,
                    "stream_url": {
                        "flv_pull_url": {"HD1": "https://example.com/live.flv"}
                    },
                }
            ]
        }
    }
    room = room_from_enter_payload(payload)
    assert room is not None
    assert room["id_str"] == "731829"
    assert flv_from_room_dict(room) == "https://example.com/live.flv"


def test_flv_from_room_dict_string_pull() -> None:
    room = {"stream_url": {"flv_pull_url": "https://example.com/sd.flv"}}
    assert flv_from_room_dict(room) == "https://example.com/sd.flv"


def test_resolve_web_rid_for_enter_prefers_explicit_web_rid() -> None:
    from unittest.mock import MagicMock

    from media2text.core.platform.douyin.live_enter import resolve_web_rid_for_enter

    client = MagicMock()
    assert (
        resolve_web_rid_for_enter(
            client,
            "7649404054766291754",
            web_rid="628224832373",
        )
        == "628224832373"
    )
    client.get.assert_not_called()


def test_resolve_web_rid_from_live_page() -> None:
    from unittest.mock import MagicMock

    from media2text.core.platform.douyin.live_enter import resolve_web_rid_from_live_page

    client = MagicMock()
    client.get.return_value.status_code = 200
    client.get.return_value.text = 'var x = {"web_rid":"369324308707"}'
    assert resolve_web_rid_from_live_page(client, "7649404054766291754") == "369324308707"
    client.get.assert_called_once()


def test_resolve_stream_via_signed_http_enter_success() -> None:
    from unittest.mock import MagicMock, patch

    from media2text.core.platform.douyin.live_enter import resolve_stream_via_signed_http_enter

    client = MagicMock()
    payload = {
        "data": {
            "data": [
                {
                    "id_str": "707628",
                    "status": 2,
                    "stream_url": {
                        "flv_pull_url": {"HD1": "https://example.com/live.flv"}
                    },
                }
            ]
        }
    }
    with (
        patch(
            "media2text.core.platform.douyin.live_enter.resolve_web_rid_for_enter",
            return_value="628224832373",
        ),
        patch(
            "media2text.core.platform.douyin.live_enter.fetch_signed_web_enter_payload",
            return_value=payload,
        ),
    ):
        url = resolve_stream_via_signed_http_enter(
            client,
            "7649404054766291754",
            sec_user_id="MS4wLjABAAAAtest",
            web_rid="628224832373",
        )
    assert url == "https://example.com/live.flv"


def test_resolve_stream_via_signed_http_enter_rejects_non_live_status() -> None:
    from unittest.mock import MagicMock, patch

    from media2text.core.platform.douyin.live_enter import resolve_stream_via_signed_http_enter

    client = MagicMock()
    payload = {
        "data": {
            "data": [
                {
                    "id_str": "707628",
                    "status": 4,
                    "stream_url": {},
                }
            ]
        }
    }
    with (
        patch(
            "media2text.core.platform.douyin.live_enter.resolve_web_rid_for_enter",
            return_value="628224832373",
        ),
        patch(
            "media2text.core.platform.douyin.live_enter.fetch_signed_web_enter_payload",
            return_value=payload,
        ),
        pytest.raises(ParseFailed, match="not streaming"),
    ):
        resolve_stream_via_signed_http_enter(
            client,
            "7649404054766291754",
            web_rid="628224832373",
        )


def test_parse_enter_payload_roundtrip() -> None:
    payload = {
        "data": {
            "data": [
                {
                    "id_str": "764937",
                    "title": "测试",
                    "stream_url": {
                        "flv_pull_url": {"HD1": "https://example.com/page.flv"}
                    },
                }
            ]
        }
    }
    from media2text.core.platform.douyin.live_enter import _parse_enter_payload

    url, room_id, title = _parse_enter_payload(
        payload,
        live_url="https://live.douyin.com/764937",
    )
    assert url == "https://example.com/page.flv"
    assert room_id == "764937"
    assert title == "测试"
