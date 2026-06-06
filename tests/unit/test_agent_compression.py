import pytest

from media2text.agent.context_compressor import (
    apply_fork_compression,
    build_compression_plan,
    estimate_tokens,
    maybe_post_turn_compress,
)
from media2text.agent.hermes_state import MessageRow, SessionDB
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def _fill_session(db: SessionDB, session_id: str, n: int) -> None:
    for i in range(n):
        db.append_message(
            session_id,
            MessageRow(role="user", content=f"turn {i} " + ("x" * 200)),
        )
        db.append_message(
            session_id,
            MessageRow(role="assistant", content=f"reply {i} " + ("y" * 200)),
        )


def test_fork_session_lineage(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "compress-thread"
    parent_id = db.create_session(display_thread_id=thread_id, title="t")
    child_id = db.fork_session(parent_id, reason="compression")

    child = db.get_session_row(child_id)
    assert child is not None
    assert child["parent_session_id"] == parent_id
    assert child["display_thread_id"] == thread_id
    assert db.get_active_session_for_thread(thread_id) == child_id
    conn.close()


def test_compression_summary_in_replay(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "replay-thread"
    parent_id = db.create_session(display_thread_id=thread_id)
    _fill_session(db, parent_id, 30)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "compression": {"protect_last_n": 4},
        }
    )
    plan = build_compression_plan(db, parent_id, cfg)
    assert plan is not None
    child_id = apply_fork_compression(
        db,
        display_thread_id=thread_id,
        parent_session_id=parent_id,
        plan=plan,
        cfg=cfg,
    )

    convo = db.get_messages_as_conversation(child_id)
    assert any("[compression_summary]" in (m.get("content") or "") for m in convo)
    assert db.get_active_session_for_thread(thread_id) == child_id
    conn.close()


def test_post_turn_compress_when_over_threshold(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "auto-compress"
    session_id = db.create_session(display_thread_id=thread_id)
    _fill_session(db, session_id, 40)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"chat": {"max_context_chars": 4000}},
            "compression": {
                "enabled": True,
                "auto_ratio": 0.01,
                "protect_last_n": 6,
            },
        }
    )
    messages = db.get_messages_as_conversation(session_id)
    assert estimate_tokens(messages) > 10

    new_session = maybe_post_turn_compress(
        db,
        display_thread_id=thread_id,
        session_id=session_id,
        messages=messages,
        cfg=cfg,
    )
    assert new_session != session_id
    row = db.get_session_row(new_session)
    assert row is not None
    assert row["parent_session_id"] == session_id
    conn.close()
