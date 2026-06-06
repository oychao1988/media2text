import time
import uuid

import pytest

from media2text.agent.hermes_state import MessageRow, SessionDB
from media2text.agent.model_tools import handle_function_call
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def _seed_messages(db: SessionDB, session_id: str, count: int) -> None:
    for i in range(count):
        text = f"message {i} keyword-alpha 关键词测试"
        if i % 50 == 0:
            text = f"needle-hit-{i} keyword-alpha 关键词测试"
        db.append_message(session_id, MessageRow(role="user", content=text))


def test_session_search_finds_keyword(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "search-thread"
    session_id = db.create_session(display_thread_id=thread_id, title="search")
    db.append_message(session_id, MessageRow(role="user", content="hello needle-hit world"))
    db.append_message(session_id, MessageRow(role="assistant", content="other text"))

    hits = db.search_messages("needle-hit")
    assert len(hits) >= 1
    assert hits[0].snippet
    conn.close()


def test_session_search_creator_scope(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    s_a = db.create_session(display_thread_id="t-a", creator_id="creator-a")
    s_b = db.create_session(display_thread_id="t-b", creator_id="creator-b")
    db.append_message(s_a, MessageRow(role="user", content="scoped-alpha marker"))
    db.append_message(s_b, MessageRow(role="user", content="scoped-alpha marker"))

    scoped = db.search_messages("scoped-alpha", creator_id="creator-a")
    assert scoped
    assert all(h.creator_id == "creator-a" for h in scoped)
    conn.close()


def test_session_search_tool_defaults_creator(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "tool-thread"
    session_id = db.create_session(display_thread_id=thread_id, creator_id="c-99")
    db.append_message(session_id, MessageRow(role="user", content="tool-default-marker"))

    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    ctx = ToolContext(cfg=cfg, conn=conn, creator_id="c-99", session_id=session_id)
    out = handle_function_call("session_search", {"query": "tool-default-marker"}, ctx)
    assert out["ok"] is True
    assert out["data"]["results"]
    conn.close()


def test_session_search_10k_p95_under_200ms(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    session_id = db.create_session(display_thread_id=str(uuid.uuid4()))
    _seed_messages(db, session_id, 10_000)

    timings: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        hits = db.search_messages("needle-hit", limit=8)
        timings.append(time.perf_counter() - t0)
        assert hits

    timings.sort()
    p95 = timings[int(len(timings) * 0.95)]
    assert p95 <= 0.2, f"P95 {p95:.3f}s exceeds 200ms"
    conn.close()
