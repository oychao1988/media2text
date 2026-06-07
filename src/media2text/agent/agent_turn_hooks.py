"""Turn-end hooks for nudge counters and background review spawn (M7a)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from media2text.agent.agent_state import AgentState, save_agent_state
from media2text.agent.background_review import REVIEW_TOOL_NAMES, spawn_background_review_thread
from media2text.agent.hermes_state import SessionDB
from media2text.core.config import AppConfig


@dataclass(frozen=True)
class ReviewFlags:
    review_memory: bool = False
    review_skills: bool = False


def compute_review_flags(
    cfg: AppConfig,
    *,
    turns_since_memory: int,
    iters_since_skill: int,
    valid_tool_names: set[str],
) -> ReviewFlags:
    review_memory = False
    review_skills = False

    interval = cfg.memory.nudge_interval
    if (
        interval > 0
        and cfg.memory.memory_enabled
        and turns_since_memory >= interval
        and "memory" in valid_tool_names
    ):
        review_memory = True

    skill_interval = cfg.skills.creation_nudge_interval
    if (
        skill_interval > 0
        and iters_since_skill >= skill_interval
        and "skill_manage" in valid_tool_names
    ):
        review_skills = True

    return ReviewFlags(review_memory=review_memory, review_skills=review_skills)


def apply_review_resets(state: AgentState, flags: ReviewFlags) -> None:
    if flags.review_memory:
        state.turns_since_memory = 0
    if flags.review_skills:
        state.iters_since_skill = 0


def maybe_spawn_background_review(
    foreground_agent: Any,
    cfg: AppConfig,
    *,
    session_id: str,
    db: SessionDB,
    messages_snapshot: list[dict[str, Any]],
    flags: ReviewFlags,
    agent_state: AgentState,
    cancelled: bool,
    has_final_text: bool,
    binding: dict[str, Any],
    creator_id: str | None,
    display_thread_id: str,
    provider_name: str | None,
    model: str,
) -> None:
    if not cfg.agent.review_enabled:
        return
    if cancelled or not has_final_text:
        return
    if not flags.review_memory and not flags.review_skills:
        return
    if agent_state.review_in_flight:
        return

    agent_state.review_in_flight = True
    save_agent_state(db, session_id, agent_state)

    spawn_background_review_thread(
        cfg=cfg,
        session_id=session_id,
        display_thread_id=display_thread_id,
        creator_id=creator_id,
        messages_snapshot=messages_snapshot,
        review_memory=flags.review_memory,
        review_skills=flags.review_skills,
        provider_name=provider_name,
        model=model,
        binding=binding,
        cached_system_prompt=agent_state.cached_system_prompt,
        llm=getattr(foreground_agent, "_llm", None),
    )


def review_allowed_tool_names(valid_tool_names: set[str]) -> frozenset[str]:
    return frozenset(n for n in REVIEW_TOOL_NAMES if n in valid_tool_names)
