"""Post-turn background memory/skill review (Hermes-aligned, M7a)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from media2text.agent.agent_state import load_agent_state, save_agent_state
from media2text.agent.hermes_state import SessionDB
from media2text.agent.profile_resolver import resolve_profile
from media2text.core.config import AppConfig

logger = logging.getLogger(__name__)

REVIEW_TOOL_NAMES = frozenset({"memory", "skill_manage", "skills_list", "skill_view"})

_MEMORY_REVIEW_PROMPT = """You are running a silent background memory review after a user conversation turn.
Review the conversation snapshot and update curated memory files using the memory tool only.

Guidelines:
- Use memory(action=add) for new durable facts worth remembering across sessions.
- Use memory(action=replace) when correcting an existing entry; old_text must match exactly one entry.
- Use memory(action=remove) to delete outdated entries.
- Prefer concise bullet-style entries. Do not duplicate facts already present.
- Target memory, user, or soul files only when justified by the conversation.
- Do not respond to the user; complete tool updates then stop."""

_SKILL_REVIEW_PROMPT = """You are running a silent background skill review after a tool-heavy turn.
Review whether workflow lessons should become or update skills using skill_manage and skills_list/skill_view.

Guidelines:
- Prefer patching existing skills over creating duplicates.
- Keep SKILL.md focused and actionable.
- Do not respond to the user; complete tool updates then stop."""

_COMBINED_REVIEW_PROMPT = """You are running a silent background review after a user conversation turn.
Update curated memory and skills as needed using the whitelisted tools only.

Follow memory guidelines (add/replace/remove) and skill guidelines (patch/create sparingly).
Do not respond to the user; complete tool updates then stop."""


def build_review_prompt(
    *,
    review_memory: bool,
    review_skills: bool,
    scope_hint: str,
) -> str:
    if review_memory and review_skills:
        base = _COMBINED_REVIEW_PROMPT
    elif review_skills:
        base = _SKILL_REVIEW_PROMPT
    else:
        base = _MEMORY_REVIEW_PROMPT
    return f"{base}\n\nActive profile scope:\n{scope_hint}"


def build_scope_hint(cfg: AppConfig, *, creator_id: str | None) -> str:
    profile = resolve_profile(creator_id=creator_id, cfg=cfg)
    slug = profile.profile_id
    if creator_id:
        return (
            f"creator:{creator_id} (profile {slug}). "
            f"All memory writes target {profile.memory_paths.profile_dir}."
        )
    return f"workspace profile ({slug}). All memory writes target {profile.memory_paths.profile_dir}."


def spawn_background_review_thread(
    *,
    cfg: AppConfig,
    session_id: str,
    display_thread_id: str,
    creator_id: str | None,
    messages_snapshot: list[dict[str, Any]],
    review_memory: bool,
    review_skills: bool,
    provider_name: str | None,
    model: str,
    binding: dict[str, Any],
    cached_system_prompt: str | None,
    llm: Any | None = None,
) -> threading.Thread:
    def _run() -> None:
        from media2text.agent.skill_provenance import BACKGROUND_REVIEW, write_origin_ctx
        from media2text.core.storage.db import connect

        with write_origin_ctx(BACKGROUND_REVIEW):
            conn = connect(cfg.ensure_workspace() / "media2text.db")
            db: SessionDB | None = None
            try:
                db = SessionDB(conn)
                scope_hint = build_scope_hint(cfg, creator_id=creator_id)
                prompt = build_review_prompt(
                    review_memory=review_memory,
                    review_skills=review_skills,
                    scope_hint=scope_hint,
                )
                from media2text.agent.ai_agent import AIAgent

                agent = AIAgent(
                    db,
                    cfg,
                    llm=llm,
                    toolset="review",
                    quiet=True,
                )
                agent.run_review_conversation(
                    display_thread_id=display_thread_id,
                    session_id=session_id,
                    user_text=prompt,
                    conversation_history=messages_snapshot,
                    binding=binding,
                    creator_id=creator_id,
                    provider_name=provider_name,
                    model=model,
                    cached_volatile=cached_system_prompt,
                )
                logger.info(
                    "background review completed session=%s memory=%s skills=%s",
                    session_id[:8],
                    review_memory,
                    review_skills,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("background review failed session=%s: %s", session_id[:8], exc)
            finally:
                try:
                    if db is not None:
                        st = load_agent_state(db, session_id)
                        st.review_in_flight = False
                        save_agent_state(db, session_id, st)
                except Exception:  # noqa: BLE001
                    pass
                conn.close()

    thread = threading.Thread(
        target=_run,
        daemon=True,
        name=f"bg-review-{session_id[:8]}",
    )
    thread.start()
    return thread
