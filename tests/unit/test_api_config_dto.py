import json

import pytest

from media2text.api.config_dto import (
    ConfigPatchDto,
    _default_api_key_env,
    _normalize_llm_provider_patch,
    apply_dto_patch,
    config_to_dto,
)
from media2text.core.config import AppConfig
from media2text.core.env_file import upsert_env_var

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


def test_config_to_dto_fills_null_summarize_defaults() -> None:
    cfg = AppConfig.model_validate(
        {
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "models": ["model-a", "model-b"],
                        }
                    ],
                    "default_provider": None,
                    "default_model": None,
                }
            }
        }
    )
    dto = config_to_dto(cfg)
    assert dto["summarizeProviderId"] == "nvidia"
    assert dto["summarizeModel"] == "model-a"
    assert dto["activeProviderId"] == "nvidia"


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


def test_llm_providers_dto_skips_probe_by_default(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "api_key_envs": ["NVIDIA_API_KEY"],
                            "models": ["m1"],
                        }
                    ]
                }
            },
        }
    )
    probe_called = {"n": 0}

    def _boom(*_a, **_k):
        probe_called["n"] += 1
        return True

    monkeypatch.setattr("media2text.api.config_dto._probe_provider_connected", _boom)
    dto = config_to_dto(cfg)
    assert dto["llmProviders"][0]["connected"] is None
    assert probe_called["n"] == 0


def test_llm_providers_dto_restores_cached_connected(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "data"
    sessions = workspace / "sessions"
    sessions.mkdir(parents=True)
    cache_path = sessions / "llm_provider_probe.json"
    cache_path.write_text(
        json.dumps(
            {
                "nvidia": {
                    "connected": True,
                    "fingerprint": "https://example.com/v1|NVIDIA_API_KEY",
                }
            }
        ),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(workspace),
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "api_key_envs": ["NVIDIA_API_KEY"],
                            "models": ["m1"],
                        }
                    ]
                }
            },
        }
    )
    dto = config_to_dto(cfg)
    assert dto["llmProviders"][0]["connected"] is True


def test_llm_providers_dto_includes_connected(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)
    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "api_key_envs": ["NVIDIA_API_KEY"],
                            "models": ["m1"],
                        }
                    ]
                }
            },
        }
    )
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(
        "media2text.api.config_dto._probe_provider_connected",
        lambda _p, api_key=None: True,
    )
    dto = config_to_dto(cfg, probe_providers=True)
    assert dto["llmProviders"][0]["connected"] is True
    assert dto["llmProviders"][0]["configured"] is True
    assert dto["llmProviders"][0]["api_key"] == "***"

    dto_reload = config_to_dto(cfg)
    assert dto_reload["llmProviders"][0]["connected"] is True


def test_providers_need_probe_when_configured_but_not_cached() -> None:
    from media2text.api.config_dto import _providers_need_probe

    assert _providers_need_probe([{"configured": True, "connected": None}]) is True
    assert _providers_need_probe([{"configured": True, "connected": True}]) is False
    assert _providers_need_probe([{"configured": False, "connected": None}]) is False


def test_patch_llm_provider_writes_api_key(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)
    monkeypatch.setattr("media2text.core.env_file.load_dotenv_file", lambda: None)

    cfg = AppConfig.model_validate({"summarize": {"llm": {"providers": []}}})
    apply_dto_patch(
        cfg,
        ConfigPatchDto(
            llmProviders=[
                {
                    "name": "nvidia",
                    "base_url": "https://example.com/v1",
                    "api_key_envs": [],
                    "models": ["m1"],
                    "api_key": "secret-key",
                }
            ]
        ),
    )
    provider = cfg.summarize.llm.providers[0]
    assert provider.api_key_envs == ["M2T_LLM_NVIDIA_API_KEY"]
    assert env_path.read_text(encoding="utf-8").strip() == "M2T_LLM_NVIDIA_API_KEY=secret-key"
    assert provider.name == "nvidia"


def test_default_api_key_env_sanitizes_name() -> None:
    assert _default_api_key_env("my-provider") == "M2T_LLM_MY_PROVIDER_API_KEY"


def test_normalize_llm_provider_ignores_masked_api_key(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    provider = _normalize_llm_provider_patch(
        {
            "name": "nvidia",
            "base_url": "https://example.com/v1",
            "api_key_envs": ["NVIDIA_API_KEY"],
            "models": [],
            "api_key": "***",
        }
    )
    assert not env_path.exists()
    assert provider.api_key_envs == ["NVIDIA_API_KEY"]


def test_upsert_env_var_replaces_existing(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\nNVIDIA_API_KEY=old\n", encoding="utf-8")
    upsert_env_var("NVIDIA_API_KEY", "new", path=env_path)
    text = env_path.read_text(encoding="utf-8")
    assert "NVIDIA_API_KEY=new" in text
    assert "FOO=bar" in text
    assert "old" not in text


def test_provider_api_key_prefers_env_file_over_stale_environ(
    tmp_path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)
    monkeypatch.setenv("NVIDIA_API_KEY", "stale-in-process")

    cfg = AppConfig.model_validate(
        {
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "api_key_envs": ["NVIDIA_API_KEY"],
                            "models": ["m1"],
                        }
                    ]
                }
            }
        }
    )
    dto = config_to_dto(cfg)
    assert dto["llmProviders"][0]["api_key"] == "***"
    assert dto["llmProviders"][0]["configured"] is True


def test_normalize_llm_provider_consolidates_api_key_envs(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    provider = _normalize_llm_provider_patch(
        {
            "name": "nvidia",
            "base_url": "https://example.com/v1",
            "api_key_envs": ["NVIDIA_API_KEY", "NVIDIA_API_KEY_2", "NVIDIA_API_KEY_3"],
            "models": ["m1"],
        }
    )
    assert provider.api_key_envs == ["NVIDIA_API_KEY"]


def test_patch_restart_hints() -> None:
    cfg = AppConfig.model_validate({"live": {"pipeline_mode": "legacy"}})
    daemon, agent = apply_dto_patch(
        cfg, ConfigPatchDto(pipelineMode="streaming", agentModel="gpt-4")
    )
    assert "pipelineMode" in daemon
    assert "agentModel" in agent


def test_config_to_dto_includes_tavily_and_bootstrap_fields(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TAVILY_API_KEY=tvly-secret\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"agent": {"distill": {"bootstrap_web_research": False}}},
        }
    )
    dto = config_to_dto(cfg)
    assert dto["tavilyConfigured"] is True
    assert dto["tavilyApiKey"] == "***"
    assert dto["tavilyApiKeyEnv"] == "TAVILY_API_KEY"
    assert dto["bootstrapWebResearch"] is False


def test_patch_tavily_api_key_writes_env(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)
    monkeypatch.setattr("media2text.core.env_file.load_dotenv_file", lambda: None)

    cfg = AppConfig.model_validate({"desktop": {"agent": {"distill": {}}}})
    apply_dto_patch(cfg, ConfigPatchDto(tavilyApiKey="tvly-new-key"))
    assert env_path.read_text(encoding="utf-8").strip() == "TAVILY_API_KEY=tvly-new-key"
    dto = config_to_dto(cfg)
    assert dto["tavilyConfigured"] is True


def test_patch_tavily_api_key_ignores_masked(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)

    cfg = AppConfig.model_validate({"desktop": {"agent": {"distill": {}}}})
    apply_dto_patch(cfg, ConfigPatchDto(tavilyApiKey="***"))
    assert not env_path.exists()


def test_patch_bootstrap_web_research() -> None:
    cfg = AppConfig.model_validate(
        {"desktop": {"agent": {"distill": {"bootstrap_web_research": True}}}}
    )
    apply_dto_patch(cfg, ConfigPatchDto(bootstrapWebResearch=False))
    assert cfg.desktop.agent.distill.bootstrap_web_research is False
    dto = config_to_dto(cfg)
    assert dto["bootstrapWebResearch"] is False
