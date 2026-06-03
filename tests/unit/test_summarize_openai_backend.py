from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import SummarizeLlmConfig, SummarizeLlmProviderConfig
from media2text.core.summarize.errors import SummarizeConfigError
from media2text.core.summarize.openai_backend import (
    OpenAISummarizeBackend,
    build_chat_kwargs,
    is_rate_limit_error,
    primary_model,
    resolve_api_key_envs,
    resolve_llm_endpoints,
    resolve_models,
    usage_from_response,
)


def _cfg(**kwargs) -> SummarizeLlmConfig:
    if "providers" not in kwargs:
        kwargs["providers"] = [
            SummarizeLlmProviderConfig(
                name="test",
                base_url="https://example.com/v1",
                api_key_envs=["KEY_A"],
                models=["m1"],
            )
        ]
    return SummarizeLlmConfig(**kwargs)


def test_extra_body_thinking_false() -> None:
    cfg = _cfg(
        thinking=False,
        providers=[
            SummarizeLlmProviderConfig(models=["deepseek-ai/deepseek-v4-pro"])
        ],
    )
    assert build_chat_kwargs(cfg, model="deepseek-ai/deepseek-v4-pro").get(
        "extra_body"
    ) == {"chat_template_kwargs": {"thinking": False}}


def test_extra_body_omitted_when_thinking_true() -> None:
    cfg = _cfg(thinking=True, providers=[SummarizeLlmProviderConfig(models=["gpt-4o"])])
    assert "extra_body" not in build_chat_kwargs(cfg, model="gpt-4o")


def test_primary_model() -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(models=["glm", "deepseek"]),
            SummarizeLlmProviderConfig(models=["gpt-4o-mini"]),
        ]
    )
    assert primary_model(cfg) == "glm"


@patch.dict("os.environ", {"KEY_A": "a", "KEY_B": "b", "OPENAI_API_KEY": "o"}, clear=True)
def test_resolve_llm_endpoints_multi_provider() -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(
                name="nvidia",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key_envs=["KEY_A", "KEY_B"],
                models=["glm", "deepseek"],
            ),
            SummarizeLlmProviderConfig(
                name="openai",
                base_url="https://api.openai.com/v1",
                api_key_envs=["OPENAI_API_KEY"],
                models=["gpt-4o-mini"],
            ),
        ]
    )
    eps = resolve_llm_endpoints(cfg)
    assert len(eps) == 5
    assert eps[0].base_url == "https://integrate.api.nvidia.com/v1"
    assert eps[0].model == "glm"
    assert eps[0].api_key_env == "KEY_A"
    assert eps[-1].base_url == "https://api.openai.com/v1"
    assert eps[-1].model == "gpt-4o-mini"
    assert resolve_api_key_envs(cfg) == ["KEY_A", "KEY_B", "OPENAI_API_KEY"]
    assert resolve_models(cfg) == ["glm", "deepseek", "gpt-4o-mini"]


@patch.dict("os.environ", {"OLLAMA_API_KEY": "ollama"}, clear=True)
def test_resolve_llm_endpoints_ollama_provider() -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(
                name="ollama",
                base_url="http://127.0.0.1:11434/v1",
                api_key_envs=["OLLAMA_API_KEY"],
                models=["qwen2.5:7b"],
            ),
        ]
    )
    eps = resolve_llm_endpoints(cfg)
    assert len(eps) == 1
    assert eps[0].base_url == "http://127.0.0.1:11434/v1"
    assert eps[0].model == "qwen2.5:7b"


def test_is_rate_limit_error() -> None:
    assert is_rate_limit_error(Exception("429 Too Many Requests"))
    assert is_rate_limit_error(SimpleNamespace(status_code=429))
    assert not is_rate_limit_error(Exception("500 internal"))


def test_usage_from_response() -> None:
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    u = usage_from_response(usage)
    assert u.prompt_tokens == 100
    assert u.completion_tokens == 50
    assert u.total_tokens == 150
    assert u.requests == 1


@patch.dict("os.environ", {"KEY_A": "a", "KEY_B": "b"}, clear=True)
def test_chat_rotates_key_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(
                api_key_envs=["KEY_A", "KEY_B"],
                models=["m1"],
            )
        ],
        log_token_usage=False,
    )
    backend = OpenAISummarizeBackend(llm=cfg)

    calls: list[str] = []

    def fake_client(key: str, *, base_url: str) -> MagicMock:
        client = MagicMock()
        if key == "a":

            def fail(**kwargs):
                calls.append(key)
                exc = Exception("429 Too Many Requests")
                exc.status_code = 429  # type: ignore[attr-defined]
                raise exc

            client.chat.completions.create = fail
        else:

            def ok(**kwargs):
                calls.append(key)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                    usage=SimpleNamespace(
                        prompt_tokens=10, completion_tokens=5, total_tokens=15
                    ),
                )

            client.chat.completions.create = ok

        return client

    monkeypatch.setattr(backend, "_openai_client", fake_client)
    out = backend._chat_once([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert calls == ["a", "b"]
    assert backend.usage.total_tokens == 15
    assert backend.active_api_key_env == "KEY_B"


@patch.dict("os.environ", {"KEY_A": "a"}, clear=True)
def test_chat_rotates_model_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(
                api_key_envs=["KEY_A"],
                models=["m1", "m2"],
            )
        ],
        log_token_usage=False,
    )
    backend = OpenAISummarizeBackend(llm=cfg)
    models_seen: list[str] = []

    client = MagicMock()

    def create(**kwargs):
        models_seen.append(kwargs["model"])
        if kwargs["model"] == "m1":
            exc = Exception("429")
            exc.status_code = 429  # type: ignore[attr-defined]
            raise exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="done"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

    client.chat.completions.create = create
    monkeypatch.setattr(backend, "_openai_client", lambda _k, *, base_url: client)

    out = backend._chat_once([{"role": "user", "content": "hi"}])
    assert out == "done"
    assert models_seen == ["m1", "m2"]
    assert backend.model == "m2"


@patch.dict(
    "os.environ",
    {"NVIDIA_KEY": "n", "OPENAI_API_KEY": "o"},
    clear=True,
)
def test_chat_falls_back_to_next_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SummarizeLlmConfig(
        providers=[
            SummarizeLlmProviderConfig(
                name="nvidia",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key_envs=["NVIDIA_KEY"],
                models=["glm"],
            ),
            SummarizeLlmProviderConfig(
                name="openai",
                base_url="https://api.openai.com/v1",
                api_key_envs=["OPENAI_API_KEY"],
                models=["gpt-4o-mini"],
            ),
        ],
        log_token_usage=False,
    )
    backend = OpenAISummarizeBackend(llm=cfg)
    seen: list[tuple[str, str]] = []

    def fake_client(key: str, *, base_url: str) -> MagicMock:
        client = MagicMock()

        def create(**kwargs):
            seen.append((base_url, kwargs["model"]))
            if "nvidia" in base_url:
                exc = Exception("429")
                exc.status_code = 429  # type: ignore[attr-defined]
                raise exc
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

        client.chat.completions.create = create
        return client

    monkeypatch.setattr(backend, "_openai_client", fake_client)
    out = backend._chat_once([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert seen[0][0] == "https://integrate.api.nvidia.com/v1"
    assert seen[-1] == ("https://api.openai.com/v1", "gpt-4o-mini")
    assert backend.provider_base_url == "https://api.openai.com/v1"


@patch.dict("os.environ", {}, clear=True)
def test_chat_raises_when_no_keys() -> None:
    cfg = SummarizeLlmConfig(
        providers=[SummarizeLlmProviderConfig(api_key_envs=["MISSING"], models=["m1"])]
    )
    backend = OpenAISummarizeBackend(llm=cfg)
    with pytest.raises(SummarizeConfigError, match="API key not set"):
        backend._chat_once([{"role": "user", "content": "hi"}])
