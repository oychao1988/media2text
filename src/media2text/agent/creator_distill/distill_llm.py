"""LLM call for creator distill bootstrap."""

from __future__ import annotations

from typing import Any, Callable

import structlog

from media2text.agent.creator_distill.render import parse_distill_json
from media2text.core.config import AppConfig
from media2text.core.summarize.errors import SummarizeConfigError
from media2text.core.summarize.factory import create_summarize_backend
from media2text.core.summarize.openai_backend import OpenAISummarizeBackend

log = structlog.get_logger()

_BOOTSTRAP_SYSTEM = """You distill a creator's public content into a structured perspective skill.
Output ONLY valid JSON with keys:
mental_models (array of {title, body, limitation}),
decision_heuristics (array of strings),
expression_dna (string),
honest_boundaries (string),
anti_patterns (array of strings),
sources (array of strings, local paths only).
Do not invent quotes. Mark uncertainty when corpus is thin."""


def _default_chat(cfg: AppConfig, messages: list[dict[str, str]]) -> str:
    if not cfg.summarize.enabled:
        raise SummarizeConfigError("summarize.enabled required for distill LLM")
    backend = create_summarize_backend(cfg)
    if not isinstance(backend, OpenAISummarizeBackend):
        raise SummarizeConfigError("distill bootstrap requires OpenAI-compatible summarize backend")
    return backend._chat_once(messages)  # noqa: SLF001


def distill_bootstrap_json(
    cfg: AppConfig,
    *,
    display_name: str,
    corpus_text: str,
    llm_fn: Callable[[list[dict[str, str]]], str] | None = None,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": _BOOTSTRAP_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Creator: {display_name}\n\n"
                f"Corpus ({len(corpus_text)} chars):\n\n{corpus_text[:100_000]}"
            ),
        },
    ]
    chat = llm_fn or (lambda m: _default_chat(cfg, m))
    raw = chat(messages)
    return parse_distill_json(raw)
