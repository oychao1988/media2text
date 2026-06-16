from media2text.core.runtime.heartbeat import heartbeat_stale_sec


def test_heartbeat_stale_sec_floor_at_90() -> None:
    assert heartbeat_stale_sec(10) == 90.0
    assert heartbeat_stale_sec(60) == 120.0
