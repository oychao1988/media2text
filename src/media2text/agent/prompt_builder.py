"""System prompt tiers for Hermes agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from media2text.agent.profile_resolver import resolve_profile
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo


@dataclass(frozen=True)
class SystemPromptParts:
    stable: str
    context: str
    volatile: str


def _manifest_summary(cfg: AppConfig, creator_id: str | None) -> str:
    if not creator_id:
        return "No creator bound; global thread."
    row = None
    try:
        from media2text.core.workspace import open_db

        conn = open_db(cfg)
        try:
            row = CreatorRepo(conn).get(creator_id)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return f"Creator {creator_id} (manifest unavailable)."
    if not row:
        return f"Creator {creator_id} not found."
    path = cfg.ensure_workspace() / "creators" / row.sec_uid / "agent-manifest.json"
    if not path.is_file():
        return f"Creator {row.sec_uid}: no agent-manifest.json yet."
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"Creator {row.sec_uid}: manifest unreadable."
    live_groups = manifest.get("live_groups") or []
    summary_path = manifest.get("summary_path")
    parts = [f"Creator sec_uid={row.sec_uid}"]
    if summary_path:
        parts.append(f"latest summary: {summary_path}")
    if live_groups:
        parts.append(f"live_groups: {len(live_groups)} entries")
    return "; ".join(parts)


def build_system_prompt(
    *,
    profile_ctx: dict[str, Any] | None = None,
    thread: dict[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> SystemPromptParts:
    cfg = cfg or AppConfig.load()
    profile = profile_ctx or resolve_profile(cfg)
    thread = thread or {}
    creator_id = thread.get("creator_id")
    binding = thread.get("binding") or {}
    context_mode = binding.get("context_mode") or thread.get("context_mode") or "both"

    stable = (
        "You are the media2text desktop agent. "
        "Use m2t_* tools for monitoring, recording, transcripts, and pipelines. "
        "Hermes tools (memory, session_search, skills_*) are available for context."
    )
    context_lines = [
        f"Profile dir: {profile.get('profile_dir')}",
        f"Context mode: {context_mode}",
        _manifest_summary(cfg, creator_id),
    ]
    volatile = f"Thread model: {binding.get('model') or thread.get('model') or 'auto'}"

    return SystemPromptParts(
        stable=stable,
        context="\n".join(context_lines),
        volatile=volatile,
    )


def frozen_system_messages(parts: SystemPromptParts) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": parts.stable},
        {"role": "system", "content": parts.context},
        {"role": "system", "content": parts.volatile},
    ]
