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
