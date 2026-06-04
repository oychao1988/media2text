from media2text.core.config import AppConfig
from media2text.core.platform.douyin.live import live_poll_interval_sec


def test_platform_poll_overrides_global() -> None:
    cfg = AppConfig.model_validate(
        {
            "platforms": {"douyin": {"live_poll_interval_sec": 15}},
            "live": {"live_poll_interval_sec": 10},
            "monitor": {"live_poll_interval_sec": 60},
        }
    )
    assert live_poll_interval_sec(cfg) == 15


def test_falls_back_to_live_then_monitor() -> None:
    cfg = AppConfig.model_validate(
        {
            "platforms": {"douyin": {"live_poll_interval_sec": 0}},
            "live": {"live_poll_interval_sec": 10},
            "monitor": {"live_poll_interval_sec": 60},
        }
    )
    assert live_poll_interval_sec(cfg) == 10

    cfg2 = AppConfig.model_validate(
        {
            "platforms": {"douyin": {"live_poll_interval_sec": 0}},
            "live": {"live_poll_interval_sec": 0},
            "monitor": {"live_poll_interval_sec": 60},
        }
    )
    assert live_poll_interval_sec(cfg2) == 60
