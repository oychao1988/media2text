"""Web search provider abstraction for Creator Distill bootstrap."""

from __future__ import annotations

from typing import Protocol

from media2text.agent.creator_distill.tavily_client import (
    TavilyClient,
    TavilySearchResponse,
    resolve_tavily_api_key,
)
from media2text.core.config import DistillConfig


class WebSearchProvider(Protocol):
    def search(self, query: str) -> TavilySearchResponse: ...


class NoneWebSearchProvider:
    """Offline / unit-test provider — always returns empty results."""

    def search(self, query: str) -> TavilySearchResponse:
        del query
        return TavilySearchResponse(answer="", results=[])


class TavilyWebSearchProvider:
    def __init__(self, *, client: TavilyClient, cfg: DistillConfig) -> None:
        self._client = client
        self._cfg = cfg

    def search(self, query: str) -> TavilySearchResponse:
        return self._client.search(
            query,
            max_results=self._cfg.web_search_max_results,
            include_answer=self._cfg.tavily_include_answer,
            search_depth=self._cfg.tavily_search_depth,
            exclude_domains=list(self._cfg.web_source_denylist),
        )


def build_web_search_provider(*, cfg: DistillConfig, api_key: str | None = None) -> WebSearchProvider:
    if cfg.web_search_provider == "none":
        return NoneWebSearchProvider()
    key = (api_key or resolve_tavily_api_key(env_key=cfg.tavily_api_key_env)).strip()
    if not key:
        return NoneWebSearchProvider()
    client = TavilyClient(
        api_key=key,
        timeout_sec=float(cfg.web_search_timeout_sec),
    )
    return TavilyWebSearchProvider(client=client, cfg=cfg)
