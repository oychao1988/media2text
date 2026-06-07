"""Background review e2e with mock LLM (M7a S2/S4/S6)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import SessionDB
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.runtime_provider import LlmCompletion, LlmToolCall, MockChatClient
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo

pytestmark = pytest.mark.agent


def _seed_creator(workspace, *, sec_uid: str, nickname: str) -> str:
    conn = connect(workspace / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name=nickname,
    )
    conn.close()
    return cid


class ReviewTrackingClient(MockChatClient):
    def __init__(self, foreground: list[LlmCompletion], review: list[LlmCompletion]) -> None:
        super().__init__(foreground)
        self._review = list(review)
        self.review_calls: list[dict] = []
        self._lock = threading.Lock()
        self._in_review = False

    def complete(self, **kwargs):
        messages = kwargs.get("messages") or []
        is_review = any(
            m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and "background memory review" in m["content"].lower()
            for m in messages
        )
        if is_review:
            with self._lock:
                self._in_review = True
                self.review_calls.append(kwargs)
                if self._review:
                    item = self._review.pop(0)
                    if item.tool_calls:
                        return item
                    return item
                return LlmCompletion(content="review done")
        return super().complete(**kwargs)


def test_background_review_writes_creator_memory(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "memory": {"nudge_interval": 1},
            "agent": {"review_enabled": True},
        }
    )
    conn = connect(ws / "media2text.db")
    db = SessionDB(conn)

    cid_a = _seed_creator(ws, sec_uid="sec_a", nickname="Creator A")
    cid_b = _seed_creator(ws, sec_uid="sec_b", nickname="Creator B")

    thread_id = "t-review"
    db.create_session(display_thread_id=thread_id, title="review", creator_id=cid_a)

    review_client = ReviewTrackingClient(
        foreground=[LlmCompletion(content="foreground reply")],
        review=[
            LlmCompletion(
                tool_calls=[
                    LlmToolCall(
                        id="rev-1",
                        name="memory",
                        arguments=json.dumps(
                            {
                                "action": "add",
                                "target": "memory",
                                "content": "creator A secret",
                            }
                        ),
                    )
                ]
            ),
            LlmCompletion(content=""),
        ],
    )

    agent = AIAgent(db, cfg=cfg, llm=review_client)
    reply = agent.run_conversation(display_thread_id=thread_id, user_text="hello")
    assert reply == "foreground reply"

    deadline = time.time() + 5.0
    while time.time() < deadline:
        profile_a = resolve_profile(creator_id=cid_a, cfg=cfg)
        mem_a = profile_a.memory_paths.memory
        if mem_a.is_file() and "creator A secret" in mem_a.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    else:
        pytest.fail("review did not write creator A memory in time")

    profile_b = resolve_profile(creator_id=cid_b, cfg=cfg)
    mem_b = profile_b.memory_paths.memory
    if mem_b.is_file():
        assert "creator A secret" not in mem_b.read_text(encoding="utf-8")

    assert review_client.review_calls
    assert review_client.review_calls[0]["model"] == review_client.review_calls[0]["model"]
    conn.close()


def test_review_denies_m2t_tools(tmp_path) -> None:
    from media2text.agent.agent_turn_hooks import review_allowed_tool_names
    from media2text.agent.model_tools import handle_function_call
    from media2text.agent.tools.m2t_handlers import ToolContext

    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    conn = connect(tmp_path / "data" / "media2text.db")
    allowed = review_allowed_tool_names({"memory", "skills_list", "skill_view"})
    ctx = ToolContext(cfg=cfg, conn=conn, allowed_tools=allowed)
    out = handle_function_call("m2t_get_live_status", "{}", ctx)
    assert out["ok"] is False
    assert out["error"]["code"] == "TOOL_DENIED"
    conn.close()
