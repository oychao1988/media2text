"""System prompt tiers for Hermes agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from media2text.agent.memory_store import (
    format_memory_block,
    load_volatile_snapshot,
    load_volatile_snapshot_for_profile,
)
from media2text.agent.profile_resolver import AgentProfileContext, resolve_profile
from media2text.agent.skill_usage import record_default_skills_use
from media2text.agent.skills_index import build_skills_index, format_skills_index_block
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
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
    thread: dict[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> SystemPromptParts:
    cfg = cfg or AppConfig.load()
    thread = thread or {}
    creator_id = thread.get("creator_id")
    if profile_ctx is None:
        profile: AgentProfileContext | dict[str, Any] = resolve_profile(
            creator_id=creator_id,
            cfg=cfg,
        )
    else:
        profile = profile_ctx
    if isinstance(profile, AgentProfileContext):
        record_default_skills_use(profile)
    binding = thread.get("binding") or {}
    context_mode = binding.get("context_mode") or thread.get("context_mode") or "both"

    skills_block = format_skills_index_block(build_skills_index(profile))
    stable_parts = [
        "You are the media2text desktop agent. "
        "Use m2t_* tools for monitoring, recording, transcripts, and pipelines. "
        "Hermes tools (memory, session_search, skills_list, skill_view) are available for context.",
    ]
    if skills_block:
        stable_parts.append(skills_block)
    stable = "\n\n".join(stable_parts)
    if isinstance(profile, AgentProfileContext):
        profile_line = f"Profile: {profile.profile_id} ({profile.memory_paths.profile_dir})"
    else:
        profile_line = f"Profile dir: {profile.get('profile_dir')}"
    context_lines = [
        profile_line,
        f"Context mode: {context_mode}",
        _manifest_summary(cfg, creator_id),
    ]
    if isinstance(profile, AgentProfileContext):
        snapshot = load_volatile_snapshot_for_profile(profile)
    else:
        snapshot = load_volatile_snapshot(cfg)
    memory_block = format_memory_block(snapshot)
    volatile_lines = [
        f"Thread model: {binding.get('model') or thread.get('model') or 'auto'}",
    ]
    if memory_block:
        volatile_lines.append(memory_block)

    return SystemPromptParts(
        stable=stable,
        context="\n".join(context_lines),
        volatile="\n\n".join(volatile_lines),
    )


def frozen_system_messages(parts: SystemPromptParts) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": parts.stable},
        {"role": "system", "content": parts.context},
        {"role": "system", "content": parts.volatile},
    ]
