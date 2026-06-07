"""OpenAI-compatible chat completions for agent loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from media2text.core.config import AppConfig, AuxiliarySlotConfig
from media2text.core.summarize.openai_backend import (
    primary_model,
    resolve_api_key_envs,
    resolve_llm_endpoints,
    resolve_provider_for_model,
)


class TurnCancelled(Exception):
    pass


@dataclass
class LlmToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LlmCompletion:
    content: str | None = None
    tool_calls: list[LlmToolCall] = field(default_factory=list)
    thinking_text: str | None = None


class ChatClient(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        cancel_event: Any = None,
    ) -> LlmCompletion: ...


def _interruptible_api_call(cancel_event, fn):
    if cancel_event is not None and cancel_event.is_set():
        raise TurnCancelled()
    result = fn()
    if cancel_event is not None and cancel_event.is_set():
        raise TurnCancelled()
    return result


def resolve_model(cfg: AppConfig, thread_model: str | None) -> str:
    model = (thread_model or "auto").strip()
    if model and model != "auto":
        return model
    return primary_model(cfg.summarize.llm)


def resolve_agent_provider(
    cfg: AppConfig,
    *,
    model: str,
    provider_name: str | None,
) -> str | None:
    """Pick LLM provider for a thread binding (model wins over stale provider_name)."""
    llm = cfg.summarize.llm
    by_model = resolve_provider_for_model(llm, model)
    if by_model:
        return by_model
    if provider_name:
        for prov in llm.providers:
            if (prov.name or "").lower() == provider_name.lower():
                return prov.name
    default = (llm.default_provider or "").strip()
    return default or None


def resolve_auxiliary_slot(
    slot: AuxiliarySlotConfig,
    *,
    cfg: AppConfig,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
) -> tuple[str | None, str]:
    """Resolve auxiliary.review / auxiliary.curator; auto falls back to main turn model."""
    model_raw = (slot.model or "auto").strip()
    if model_raw == "auto":
        model = resolve_model(cfg, fallback_model)
    else:
        model = model_raw

    provider_raw = (slot.provider or "auto").strip()
    if provider_raw == "auto":
        provider_name = resolve_agent_provider(
            cfg,
            model=model,
            provider_name=fallback_provider,
        )
    else:
        provider_name = provider_raw
    return provider_name, model


def build_openai_client(cfg: AppConfig, *, provider_name: str | None = None) -> ChatClient:
    return OpenAIChatClient(cfg, provider_name=provider_name)


class OpenAIChatClient:
    def __init__(self, cfg: AppConfig, *, provider_name: str | None = None) -> None:
        self._cfg = cfg
        self._provider_name = provider_name
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore[reportMissingImports]
        except ImportError as exc:
            raise RuntimeError(
                'OpenAI SDK not installed; run: pip install -e ".[transcribe-cloud]"'
            ) from exc

        llm = self._cfg.summarize.llm
        endpoints = resolve_llm_endpoints(llm)
        if not endpoints:
            envs = ", ".join(resolve_api_key_envs(llm)) or "(none configured)"
            raise RuntimeError(f"LLM API key not set; export one of: {envs}")
        endpoint = endpoints[0]
        if self._provider_name:
            for ep in endpoints:
                if ep.provider_name.lower() == self._provider_name.lower():
                    endpoint = ep
                    break

        kwargs: dict[str, Any] = {
            "api_key": endpoint.api_key,
            "timeout": float(self._cfg.desktop.agent.llm_timeout_sec),
        }
        if endpoint.base_url:
            kwargs["base_url"] = endpoint.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        cancel_event=None,
    ) -> LlmCompletion:
        def _call() -> LlmCompletion:
            client = self._ensure_client()
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": self._cfg.summarize.llm.temperature,
                "max_tokens": self._cfg.summarize.llm.max_output_tokens,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = client.chat.completions.create(**kwargs)
            choice = resp.choices[0].message
            tool_calls: list[LlmToolCall] = []
            for tc in choice.tool_calls or []:
                fn = tc.function
                tool_calls.append(
                    LlmToolCall(
                        id=tc.id,
                        name=fn.name,
                        arguments=fn.arguments or "{}",
                    )
                )
            return LlmCompletion(
                content=choice.content,
                tool_calls=tool_calls,
                thinking_text=getattr(choice, "reasoning_content", None),
            )

        return _interruptible_api_call(cancel_event, _call)


class MockChatClient:
    """Scripted responses for unit tests."""

    def __init__(self, script: list[LlmCompletion]) -> None:
        self._script = list(script)
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        cancel_event=None,
    ) -> LlmCompletion:
        _ = cancel_event
        self.calls.append({"messages": messages, "tools": tools, "model": model})
        if self._index >= len(self._script):
            return LlmCompletion(content="(mock exhausted)")
        out = self._script[self._index]
        self._index += 1
        return out


def tool_result_text(result: dict[str, Any]) -> str:
    if result.get("ok"):
        data = result.get("data")
        return json.dumps(data if data is not None else {}, ensure_ascii=False, indent=2)
    err = result.get("error") or {}
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err, ensure_ascii=False)
    return str(err)
