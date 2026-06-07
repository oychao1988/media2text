import pytest

from media2text.agent.agent_state import AgentState, load_agent_state, save_agent_state
from media2text.agent.hermes_state import SessionDB
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_agent_state_column_exists(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "agent_state_json" in cols
    conn.close()


def test_save_and_load_agent_state(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    sid = db.create_session(display_thread_id="t1", title="hi")
    state = AgentState(turns_since_memory=3, review_in_flight=False)
    save_agent_state(db, sid, state)
    loaded = load_agent_state(db, sid)
    assert loaded.turns_since_memory == 3
    conn.close()


def test_copy_agent_state_on_fork(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    parent = db.create_session(display_thread_id="t-fork", title="fork")
    save_agent_state(db, parent, AgentState(turns_since_memory=7))
    child = db.fork_session(parent, reason="compression")
    db.copy_agent_state(parent, child)
    loaded = load_agent_state(db, child)
    assert loaded.turns_since_memory == 7
    conn.close()
