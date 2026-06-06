import pytest

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import MessageRow, SessionDB
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_session_db_create_append_replay(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "thread-1"
    session_id = db.create_session(
        display_thread_id=thread_id,
        title="t",
        creator_id=None,
        model="auto",
        context_mode="both",
    )
    assert session_id
    assert db.get_active_session_for_thread(thread_id) == session_id

    db.append_message(session_id, MessageRow(role="user", content="hi"))
    db.append_message(session_id, MessageRow(role="assistant", content="hello"))

    convo = db.get_messages_as_conversation(session_id)
    assert convo == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    conn.close()


def test_ai_agent_mock_llm_persists(tmp_path) -> None:
    from media2text.agent.runtime_provider import LlmCompletion, MockChatClient

    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "thread-echo"
    db.create_session(display_thread_id=thread_id, title="echo")
    agent = AIAgent(db, llm=MockChatClient([LlmCompletion(content="mock reply")]))
    reply = agent.run_conversation(display_thread_id=thread_id, user_text="ping")
    assert reply == "mock reply"
    msgs = db.get_messages(thread_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "mock reply"
    conn.close()


def test_global_thread_nullable_creator(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "global-thread"
    db.create_session(display_thread_id=thread_id, creator_id=None)
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    assert row["creator_id"] is None
    conn.close()
