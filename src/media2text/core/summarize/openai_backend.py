from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

import structlog

from media2text.core.config import SummarizeLlmConfig
from media2text.core.summarize.base import LlmUsage
from media2text.core.summarize.chunker import format_chunk
from media2text.core.summarize.errors import SummarizeConfigError, SummarizeError
from media2text.core.summarize.prompts import build_messages

log = structlog.get_logger()


class SummarizeBackend(Protocol):
    @property
    def engine(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_base_url(self) -> str | None: ...

    @property
    def usage(self) -> LlmUsage: ...

    def summarize_text(self, profile: str, text: str, *, merge_pass: bool = False) -> str: ...

    def summarize_chunks(
        self, profile: str, chunks: list[str], *, merge_pass: bool = False
    ) -> str: ...


@dataclass(frozen=True)
class LlmEndpoint:
    provider_name: str
    base_url: str
    model: str
    api_key_env: str
    api_key: str


def primary_model(cfg: SummarizeLlmConfig) -> str:
    for prov in cfg.providers:
        if prov.models:
            return prov.models[0]
    return "unknown"


def resolve_api_key_envs(cfg: SummarizeLlmConfig) -> list[str]:
    seen: set[str] = set()
    envs: list[str] = []
    for prov in cfg.providers:
        for env_name in prov.api_key_envs:
            if env_name and env_name not in seen:
                seen.add(env_name)
                envs.append(env_name)
    return envs


def resolve_models(cfg: SummarizeLlmConfig) -> list[str]:
    seen: set[str] = set()
    models: list[str] = []
    for prov in cfg.providers:
        for name in prov.models:
            if name and name not in seen:
                seen.add(name)
                models.append(name)
    return models


def resolve_llm_endpoints(cfg: SummarizeLlmConfig) -> list[LlmEndpoint]:
    endpoints: list[LlmEndpoint] = []
    for prov in cfg.providers:
        if not prov.models or not prov.api_key_envs:
            continue
        for model in prov.models:
            if not model:
                continue
            for env_name in prov.api_key_envs:
                key = os.environ.get(env_name, "").strip()
                if key:
                    endpoints.append(
                        LlmEndpoint(
                            provider_name=prov.name or prov.base_url,
                            base_url=prov.base_url,
                            model=model,
                            api_key_env=env_name,
                            api_key=key,
                        )
                    )
    return endpoints


def build_chat_kwargs(cfg: SummarizeLlmConfig, *, model: str) -> dict:
    kwargs: dict = {
        "model": model,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_output_tokens,
    }
    if not cfg.thinking and "deepseek" in model.lower():
        kwargs["extra_body"] = {"chat_template_kwargs": {"thinking": False}}
    return kwargs


def is_rate_limit_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "too many requests" in text


def usage_from_response(usage: Any) -> LlmUsage:
    if usage is None:
        return LlmUsage(requests=1)
    return LlmUsage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        requests=1,
    )


class OpenAISummarizeBackend:
    def __init__(self, *, llm: SummarizeLlmConfig, engine: str = "openai") -> None:
        self._llm = llm
        self._engine = engine
        self._usage = LlmUsage()
        endpoints = resolve_llm_endpoints(llm)
        self._active_model = endpoints[0].model if endpoints else primary_model(llm)
        self._active_api_key_env: str | None = None
        self._active_base_url: str | None = None
        self._active_provider: str | None = None

    @property
    def usage(self) -> LlmUsage:
        return self._usage.copy()

    @property
    def active_api_key_env(self) -> str | None:
        return self._active_api_key_env

    def _openai_client(self, api_key: str, *, base_url: str):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SummarizeConfigError(
                'OpenAI SDK not installed; run: pip install -e ".[transcribe-cloud]"'
            ) from exc

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    def _record_usage(self, resp: Any, *, endpoint: LlmEndpoint) -> LlmUsage:
        req_usage = usage_from_response(getattr(resp, "usage", None))
        self._usage.add(req_usage)
        self._active_model = endpoint.model
        self._active_api_key_env = endpoint.api_key_env
        self._active_base_url = endpoint.base_url
        self._active_provider = endpoint.provider_name
        if self._llm.log_token_usage:
            log.info(
                "summarize_llm_request",
                provider=endpoint.provider_name,
                base_url=endpoint.base_url,
                model=endpoint.model,
                api_key_env=endpoint.api_key_env,
                prompt_tokens=req_usage.prompt_tokens,
                completion_tokens=req_usage.completion_tokens,
                total_tokens=req_usage.total_tokens,
            )
        return req_usage

    def _chat_once(self, messages: list[dict[str, str]]) -> str:
        endpoints = resolve_llm_endpoints(self._llm)
        if not endpoints:
            envs = ", ".join(resolve_api_key_envs(self._llm)) or "(none configured)"
            raise SummarizeConfigError(
                f"Summarize API key not set; export one of: {envs}"
            )

        last_err: Exception | None = None

        for endpoint in endpoints:
            chat_kwargs = build_chat_kwargs(self._llm, model=endpoint.model)
            client = self._openai_client(
                endpoint.api_key, base_url=endpoint.base_url
            )
            for attempt in range(2):
                try:
                    resp = client.chat.completions.create(
                        messages=cast(Any, messages),
                        **chat_kwargs,
                    )
                    content = resp.choices[0].message.content
                    if not content or not str(content).strip():
                        raise SummarizeError("empty LLM response")
                    self._record_usage(resp, endpoint=endpoint)
                    return str(content).strip()
                except SummarizeError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    if is_rate_limit_error(exc):
                        log.warning(
                            "summarize_llm_rate_limited",
                            provider=endpoint.provider_name,
                            base_url=endpoint.base_url,
                            model=endpoint.model,
                            api_key_env=endpoint.api_key_env,
                            error=str(exc),
                        )
                        break
                    if attempt == 0:
                        time.sleep(1.0)
                        continue
                    raise SummarizeError(f"LLM request failed: {exc}") from exc

        raise SummarizeError(
            f"LLM request failed after trying {len(endpoints)} endpoint(s): {last_err}"
        ) from last_err

    def summarize_text(
        self, profile: str, text: str, *, merge_pass: bool = False
    ) -> str:
        messages = build_messages(profile, text, merge_pass=merge_pass)
        return self._chat_once(messages)

    def summarize_chunks(
        self, profile: str, chunks: list[str], *, merge_pass: bool = False
    ) -> str:
        if not chunks:
            raise SummarizeError("no chunks to summarize")
        if len(chunks) == 1:
            return self.summarize_text(profile, chunks[0], merge_pass=merge_pass)

        partials: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            partial = self.summarize_text(
                profile,
                f"[片段 {i}/{len(chunks)}]\n{chunk}",
                merge_pass=False,
            )
            partials.append(partial)

        combined = "\n\n---\n\n".join(
            f"### 片段 {i} 摘要\n{p}" for i, p in enumerate(partials, start=1)
        )
        return self.summarize_text(profile, combined, merge_pass=True)

    @property
    def model(self) -> str:
        return self._active_model

    @property
    def engine(self) -> str:
        return self._engine

    @property
    def provider_base_url(self) -> str | None:
        return self._active_base_url


def summarize_segment_chunks(
    backend: OpenAISummarizeBackend,
    profile: str,
    segment_chunks: list[list],
) -> tuple[str, int]:
    """segment_chunks: list of list[TranscriptSegment] from chunker."""
    texts = [format_chunk(c) for c in segment_chunks]
    markdown = backend.summarize_chunks(profile, texts)
    return markdown, len(texts)
