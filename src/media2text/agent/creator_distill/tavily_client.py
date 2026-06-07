"""Tavily Search/Extract HTTP client for Creator Distill bootstrap web research."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from media2text.core.env_file import env_file_path, read_env_var

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class TavilyResult:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class TavilySearchResponse:
    answer: str
    results: list[TavilyResult]


@dataclass(frozen=True)
class TavilyExtractResult:
    url: str
    raw_content: str


@dataclass(frozen=True)
class TavilyExtractResponse:
    results: list[TavilyExtractResult]


def resolve_tavily_api_key(*, env_key: str = "TAVILY_API_KEY") -> str:
    """Prefer project ``.env`` on disk over stale ``os.environ``."""
    val = read_env_var(env_key, path=env_file_path()).strip()
    if not val:
        val = os.environ.get(env_key, "").strip()
    if val:
        os.environ[env_key] = val
    return val


class TavilyClient:
    BASE = "https://api.tavily.com"

    def __init__(self, *, api_key: str, timeout_sec: float = 60.0) -> None:
        self._api_key = api_key
        self._timeout = timeout_sec

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        include_answer: bool = True,
        search_depth: str = "basic",
        exclude_domains: list[str] | None = None,
    ) -> TavilySearchResponse:
        payload: dict[str, object] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": include_answer,
            "search_depth": search_depth,
        }
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        data = self._post_json("/search", payload)
        results = [
            TavilyResult(
                title=str(r.get("title") or ""),
                url=str(r.get("url") or ""),
                content=str(r.get("content") or ""),
            )
            for r in data.get("results") or []
        ]
        return TavilySearchResponse(answer=str(data.get("answer") or ""), results=results)

    def extract(self, urls: list[str]) -> TavilyExtractResponse:
        if not urls:
            return TavilyExtractResponse(results=[])
        payload = {
            "api_key": self._api_key,
            "urls": urls,
        }
        data = self._post_json("/extract", payload)
        results = [
            TavilyExtractResult(
                url=str(r.get("url") or ""),
                raw_content=str(r.get("raw_content") or r.get("content") or ""),
            )
            for r in data.get("results") or []
        ]
        return TavilyExtractResponse(results=results)

    def _post_json(self, path: str, payload: dict, *, max_retries: int = 2) -> dict:
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.BASE}{path}",
                    json=payload,
                    timeout=self._timeout,
                )
                if resp.status_code == 401:
                    resp.raise_for_status()
                if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                    time.sleep(delay)
                    delay *= 3
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 401 or attempt >= max_retries:
                    raise
                time.sleep(delay)
                delay *= 3
        raise last_exc or RuntimeError("tavily request failed")
