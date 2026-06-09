import json

from media2text.core.platform.douyin.parse import parse_profile_live


def test_parse_profile_live_room_data_web_rid_and_flv() -> None:
    room_data = {
        "status": 2,
        "title": "今天这么多人？进来聊吧",
        "owner": {"web_rid": "628224832373"},
        "stream_url": {
            "flv_pull_url": {"HD1": "https://example.com/live.flv"},
        },
    }
    payload = {
        "user": {
            "room_id": "7649404054766291754",
            "live_status": 1,
            "nickname": "产品老曾（职场进阶）",
            "room_data": json.dumps(room_data),
        }
    }
    info = parse_profile_live(payload)
    assert info.is_live is True
    assert info.room_id == "7649404054766291754"
    assert info.web_rid == "628224832373"
    assert info.stream_flv_url == "https://example.com/live.flv"
    assert info.title == "今天这么多人？进来聊吧"
