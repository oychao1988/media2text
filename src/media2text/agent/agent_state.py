"""Persisted per-session agent counters and prompt cache (M7a)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from media2text.agent.hermes_state import SessionDB


@dataclass
class AgentState:
    turns_since_memory: int = 0
    iters_since_skill: int = 0
    review_in_flight: bool = False
    cached_system_prompt: str | None = None
    prompt_cache_key: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "turns_since_memory": self.turns_since_memory,
                "iters_since_skill": self.iters_since_skill,
                "review_in_flight": self.review_in_flight,
                "cached_system_prompt": self.cached_system_prompt,
                "prompt_cache_key": self.prompt_cache_key,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> AgentState:
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(
            turns_since_memory=int(data.get("turns_since_memory") or 0),
            iters_since_skill=int(data.get("iters_since_skill") or 0),
            review_in_flight=bool(data.get("review_in_flight")),
            cached_system_prompt=data.get("cached_system_prompt"),
            prompt_cache_key=data.get("prompt_cache_key"),
        )


def load_agent_state(db: SessionDB, session_id: str) -> AgentState:
    row = db.get_session_row(session_id)
    if row is None:
        raise KeyError(session_id)
    return AgentState.from_json(row["agent_state_json"])


def save_agent_state(db: SessionDB, session_id: str, state: AgentState) -> None:
    db.update_agent_state_json(session_id, state.to_json())


def hydrate_turns_since_memory(
    db: SessionDB,
    session_id: str,
    *,
    nudge_interval: int,
) -> AgentState:
    """Replay-safe: prior user turns mod interval when column was empty."""
    state = load_agent_state(db, session_id)
    if nudge_interval <= 0:
        return state
    prior = db.count_user_messages(session_id)
    if prior > 0 and state.turns_since_memory == 0 and not row_has_agent_state(db, session_id):
        state.turns_since_memory = prior % nudge_interval
    return state


def row_has_agent_state(db: SessionDB, session_id: str) -> bool:
    row = db.get_session_row(session_id)
    if row is None:
        return False
    raw = row["agent_state_json"]
    return bool(raw and str(raw).strip())
