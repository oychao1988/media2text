"""Prompt tier builder (M0 stub)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from media2text.core.config import AppConfig


@dataclass(frozen=True)
class SystemPromptParts:
    stable: str
    context: str
    volatile: str


def build_system_prompt(
    *,
    profile_ctx: dict[str, Any] | None = None,
    thread: dict[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> SystemPromptParts:
    """Return non-empty stable/context/volatile placeholders for M0."""
    _ = profile_ctx, thread, cfg
    return SystemPromptParts(
        stable="You are the media2text desktop agent (M0 stub).",
        context="Workspace: local data directory; thread binding loaded at turn start.",
        volatile="Volatile snapshot: timestamp frozen at turn start (M0).",
    )
