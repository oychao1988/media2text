import pytest

from media2text.agent.agent_turn_hooks import compute_review_flags
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_memory_nudge_fires_at_interval() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws", "memory": {"nudge_interval": 3}})
    flags = compute_review_flags(
        cfg,
        turns_since_memory=3,
        iters_since_skill=0,
        valid_tool_names={"memory", "skills_list"},
    )
    assert flags.review_memory is True
    assert flags.review_skills is False


def test_skill_nudge_disabled_without_skill_manage() -> None:
    cfg = AppConfig.model_validate(
        {"workspace": "/tmp/ws", "skills": {"creation_nudge_interval": 2}}
    )
    flags = compute_review_flags(
        cfg,
        turns_since_memory=0,
        iters_since_skill=99,
        valid_tool_names={"memory", "skills_list"},
    )
    assert flags.review_skills is False


def test_skill_nudge_fires_with_skill_manage() -> None:
    cfg = AppConfig.model_validate(
        {"workspace": "/tmp/ws", "skills": {"creation_nudge_interval": 2}}
    )
    flags = compute_review_flags(
        cfg,
        turns_since_memory=0,
        iters_since_skill=2,
        valid_tool_names={"memory", "skill_manage", "skills_list"},
    )
    assert flags.review_skills is True


def test_hydrate_modulo_on_resume(tmp_path) -> None:
    from media2text.agent.agent_state import hydrate_turns_since_memory
    from media2text.agent.hermes_state import MessageRow, SessionDB
    from media2text.core.storage.db import connect

    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    sid = db.create_session(display_thread_id="t-resume", title="r")
    for i in range(7):
        db.append_message(sid, MessageRow(role="user", content=f"msg {i}"))
    state = hydrate_turns_since_memory(db, sid, nudge_interval=10)
    assert state.turns_since_memory == 7
    conn.close()
