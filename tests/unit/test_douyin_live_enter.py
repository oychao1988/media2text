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
