import json

import pytest

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import SessionDB
from media2text.agent.model_tools import reset_memory_store
from media2text.agent.runtime_provider import LlmCompletion, LlmToolCall, MockChatClient
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_run_conversation_tool_then_answer_replays_fact(tmp_path) -> None:
    reset_memory_store()
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-replay"
    db.create_session(display_thread_id=thread_id, title="test")

    mock = MockChatClient(
        [
            LlmCompletion(
                tool_calls=[
                    LlmToolCall(
                        id="call-1",
                        name="memory",
                        arguments=json.dumps(
                            {"action": "write", "key": "color", "value": "azure"}
                        ),
                    )
                ]
            ),
            LlmCompletion(content="The stored color is azure."),
        ]
    )
    events: list[dict] = []

    agent = AIAgent(db, llm=mock)
    reply = agent.run_conversation(
        display_thread_id=thread_id,
        user_text="remember azure",
        emit=events.append,
    )

    assert reply == "The stored color is azure."
    first_user = [m for m in mock.calls[0]["messages"] if m.get("role") == "user"]
    assert first_user[-1]["content"] == "remember azure"
    # Second LLM call should include tool result with azure
    tool_msgs = [m for m in mock.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs
    assert "azure" in tool_msgs[0]["content"]

    types = [e["type"] for e in events]
    assert "turn.start" in types
    assert "tool.start" in types
    assert "tool.result" in types
    assert "turn.end" in types

    rows = db.get_messages(thread_id)
    roles = [r["role"] for r in rows]
    assert roles.count("tool") == 1
    conn.close()


def test_iteration_budget_stops_after_max_turns(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-budget"
    db.create_session(display_thread_id=thread_id, title="test")

    infinite_tools = LlmCompletion(
        tool_calls=[
            LlmToolCall(
                id="call-loop",
                name="skills_list",
                arguments="{}",
            )
        ]
    )
    mock = MockChatClient([infinite_tools] * 30)
    cfg = __import__("media2text.core.config", fromlist=["AppConfig"]).AppConfig.model_validate(
        {"workspace": str(tmp_path / "data"), "agent": {"max_turns": 3}}
    )
    agent = AIAgent(db, cfg=cfg, llm=mock)
    reply = agent.run_conversation(
        display_thread_id=thread_id,
        user_text="loop",
    )
    assert "迭代次数" in reply
    assert len(mock.calls) == 3
    conn.close()
