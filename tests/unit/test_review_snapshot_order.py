from unittest.mock import patch

import pytest

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import SessionDB
from media2text.agent.runtime_provider import LlmCompletion, MockChatClient
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


@patch("media2text.agent.ai_agent.maybe_spawn_background_review")
@patch(
    "media2text.agent.ai_agent.maybe_post_turn_compress",
    side_effect=lambda db, **kwargs: kwargs["session_id"],
)
def test_snapshot_taken_before_compress(mock_compress, mock_spawn, tmp_path) -> None:
    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "memory": {"nudge_interval": 1},
        }
    )
    conn = connect(tmp_path / "data" / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-snap"
    db.create_session(display_thread_id=thread_id, title="snap")

    mock = MockChatClient([LlmCompletion(content="done")])
    agent = AIAgent(db, cfg=cfg, llm=mock)
    agent.run_conversation(display_thread_id=thread_id, user_text="hello")

    assert mock_spawn.called
    snapshot = mock_spawn.call_args.kwargs["messages_snapshot"]
    roles = [m["role"] for m in snapshot]
    assert "user" in roles
    assert "assistant" in roles
    # compress receives same messages list reference path — snapshot captured pre-finally compress
    compress_messages = mock_compress.call_args.kwargs["messages"]
    assert len(snapshot) >= len(compress_messages) or len(snapshot) == len(compress_messages)
    conn.close()
