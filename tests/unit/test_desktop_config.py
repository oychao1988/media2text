from media2text.core.config import AppConfig


def test_live_auto_record_defaults_true() -> None:
    cfg = AppConfig.model_validate({"live": {}})
    assert cfg.live.auto_record is True


def test_douyin_live_poll_interval() -> None:
    cfg = AppConfig.model_validate(
        {"platforms": {"douyin": {"live_poll_interval_sec": 15}}}
    )
    assert cfg.platforms.douyin.live_poll_interval_sec == 15


def test_summarize_default_provider_model() -> None:
    cfg = AppConfig.model_validate(
        {
            "summarize": {
                "llm": {
                    "default_provider": "nvidia",
                    "default_model": "deepseek-ai/deepseek-v4-pro",
                }
            }
        }
    )
    assert cfg.summarize.llm.default_provider == "nvidia"
    assert cfg.summarize.llm.default_model == "deepseek-ai/deepseek-v4-pro"


def test_desktop_section() -> None:
    cfg = AppConfig.model_validate({"desktop": {"api_port": 8765}})
    assert cfg.desktop.api_port == 8765
    assert cfg.desktop.chat.default_model == "auto"
