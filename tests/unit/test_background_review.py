from unittest.mock import MagicMock, patch

import pytest

from media2text.agent.agent_turn_hooks import ReviewFlags, maybe_spawn_background_review
from media2text.agent.background_review import REVIEW_TOOL_NAMES, build_review_prompt
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_review_tool_whitelist() -> None:
    assert REVIEW_TOOL_NAMES == frozenset(
        {"memory", "skill_manage", "skills_list", "skill_view"}
    )


def test_build_review_prompt_memory_only() -> None:
    prompt = build_review_prompt(
        review_memory=True,
        review_skills=False,
        scope_hint="creator:abc",
    )
    assert "memory" in prompt.lower()
    assert "creator:abc" in prompt


@patch("media2text.agent.agent_turn_hooks.spawn_background_review_thread")
def test_spawn_skips_when_review_in_flight(mock_spawn, tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    agent = MagicMock()
    from media2text.agent.agent_state import AgentState

    state = AgentState(review_in_flight=True)
    maybe_spawn_background_review(
        agent,
        cfg,
        session_id="s1",
        db=MagicMock(),
        messages_snapshot=[],
        flags=ReviewFlags(review_memory=True),
        agent_state=state,
        cancelled=False,
        has_final_text=True,
        binding={},
        creator_id=None,
        display_thread_id="t1",
        provider_name="openai",
        model="gpt-4o-mini",
    )
    mock_spawn.assert_not_called()


@patch("media2text.agent.agent_turn_hooks.spawn_background_review_thread")
def test_spawn_skips_when_cancelled(mock_spawn, tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    from media2text.agent.agent_state import AgentState

    state = AgentState(review_in_flight=False)
    maybe_spawn_background_review(
        MagicMock(),
        cfg,
        session_id="s1",
        db=MagicMock(),
        messages_snapshot=[{"role": "user", "content": "hi"}],
        flags=ReviewFlags(review_memory=True),
        agent_state=state,
        cancelled=True,
        has_final_text=True,
        binding={},
        creator_id=None,
        display_thread_id="t1",
        provider_name="openai",
        model="gpt-4o-mini",
    )
    mock_spawn.assert_not_called()
