from media2text.core.config import LiveConfig


def test_live_config_recording_defaults() -> None:
    lc = LiveConfig()
    assert lc.live_poll_interval_sec == 20
    assert lc.offline_confirm_polls == 3
    assert lc.ffmpeg_exit_recheck is True
    assert lc.max_reconnect_attempts == 2
    assert lc.min_recording_sec_before_offline_end == 45
