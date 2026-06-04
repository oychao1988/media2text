import pytest

from media2text.api.config_dto import ConfigPatchDto, apply_dto_patch, config_to_dto
from media2text.core.config import AppConfig

pytestmark = pytest.mark.desktop


def test_config_to_dto_includes_poll_and_auto_record() -> None:
    cfg = AppConfig.model_validate(
        {
            "live": {"live_poll_interval_sec": 12, "auto_record": False},
            "desktop": {"theme": "dark"},
        }
    )
    dto = config_to_dto(cfg)
    assert dto["livePollInterval"] == 12
    assert dto["autoRecord"] is False
    assert dto["theme"] == "dark"


def test_apply_patch_theme_and_auto_record() -> None:
    cfg = AppConfig.model_validate({"live": {"auto_record": True}})
    apply_dto_patch(cfg, ConfigPatchDto(theme="dark", autoRecord=False))
    assert cfg.desktop.theme == "dark"
    assert cfg.live.auto_record is False


def test_feishu_webhook_empty_does_not_clear() -> None:
    cfg = AppConfig.model_validate(
        {"notify": {"feishu": {"webhook_url": "https://example.com/hook"}}}
    )
    apply_dto_patch(cfg, ConfigPatchDto(feishuWebhookUrl=""))
    assert cfg.notify.feishu.webhook_url == "https://example.com/hook"


def test_clear_feishu_webhook() -> None:
    cfg = AppConfig.model_validate(
        {"notify": {"feishu": {"webhook_url": "https://example.com/hook"}}}
    )
    apply_dto_patch(cfg, ConfigPatchDto(clearFeishuWebhook=True))
    assert cfg.notify.feishu.webhook_url == ""


def test_patch_restart_hints() -> None:
    cfg = AppConfig.model_validate({"live": {"pipeline_mode": "legacy"}})
    daemon, agent = apply_dto_patch(
        cfg, ConfigPatchDto(pipelineMode="streaming", agentModel="gpt-4")
    )
    assert "pipelineMode" in daemon
    assert "agentModel" in agent
