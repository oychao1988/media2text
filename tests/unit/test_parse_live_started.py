from media2text.core.platform.douyin.parse import (
    optional_platform_live_started_at,
    parse_reflow_room,
)


def test_optional_platform_live_started_at_unix_sec() -> None:
    iso = optional_platform_live_started_at({"create_time": 1710000000})
    assert iso is not None
    assert iso.startswith("2024-")


def test_optional_platform_live_started_at_missing() -> None:
    assert optional_platform_live_started_at({}) is None


def test_parse_reflow_room_includes_platform_live_started_at() -> None:
    payload = {
        "room": {
            "id_str": "7318296342189919011",
            "status": 2,
            "create_time": 1710000000,
            "stream_url": {"flv_pull_url": {"HD1": "https://example.com/x.flv"}},
            "owner": {"nickname": "anchor"},
        }
    }
    info = parse_reflow_room(payload)
    assert info.platform_live_started_at is not None
