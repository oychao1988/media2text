from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.summarize.errors import SummarizeConfigError
from media2text.core.summarize.openai_backend import (
    OpenAISummarizeBackend,
    SummarizeBackend,
    resolve_api_key_envs,
    resolve_llm_endpoints,
)

_SUPPORTED_ENGINES = frozenset({"openai"})


def summarize_engine_available(cfg: AppConfig) -> tuple[bool, str | None]:
    if not cfg.summarize.enabled:
        return False, "summarize.enabled is false in config"
    engine = cfg.summarize.engine
    if engine not in _SUPPORTED_ENGINES:
        return False, f"Unsupported summarize engine: {engine}"
    try:
        import openai  # noqa: F401
    except ImportError:
        return False, 'openai SDK not installed; pip install -e ".[transcribe-cloud]"'
    if not resolve_llm_endpoints(cfg.summarize.llm):
        envs = ", ".join(resolve_api_key_envs(cfg.summarize.llm))
        return False, f"Summarize API key not set; export one of: {envs}"
    return True, None


def create_summarize_backend(cfg: AppConfig) -> SummarizeBackend:
    if not cfg.summarize.enabled:
        raise SummarizeConfigError(
            "summarize.enabled is false; set summarize.enabled: true in config.yaml"
        )
    if not cfg.summarize.llm.providers:
        raise SummarizeConfigError(
            "summarize.llm.providers must include at least one provider"
        )
    engine = cfg.summarize.engine
    if engine == "openai":
        return OpenAISummarizeBackend(llm=cfg.summarize.llm, engine=engine)
    raise SummarizeConfigError(f"Unsupported summarize engine: {engine}")
