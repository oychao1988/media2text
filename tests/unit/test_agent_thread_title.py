import pytest

from media2text.agent.hermes_state import SessionDB
from media2text.agent.thread_title import (
    fallback_title,
    is_placeholder_title,
    maybe_auto_title_thread,
    suggest_thread_title,
)
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_is_placeholder_title() -> None:
    assert is_placeholder_title(None)
    assert is_placeholder_title("")
    assert is_placeholder_title("Agent")
    assert is_placeholder_title("全局 Agent")
    assert is_placeholder_title("新对话")
    assert not is_placeholder_title("直播复盘要点")


def test_fallback_title_truncates_long_user_text() -> None:
    title = fallback_title("这是一段很长的问题" * 5)
    assert title.endswith("…")
    assert len(title) <= 25


def test_maybe_auto_title_skips_custom_title(tmp_path, monkeypatch) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-custom"
    db.create_session(display_thread_id=thread_id, title="我的会话")

    called = False

    def _fake_suggest(*_args, **_kwargs):
        nonlocal called
        called = True
        return "不应写入"

    monkeypatch.setattr(
        "media2text.agent.thread_title.suggest_thread_title",
        _fake_suggest,
    )
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    assert (
        maybe_auto_title_thread(
            db,
            cfg,
            thread_id,
            user_text="hello",
            assistant_text="world",
        )
        is None
    )
    assert not called
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    assert row["title"] == "我的会话"
    conn.close()


def test_maybe_auto_title_updates_placeholder(tmp_path, monkeypatch) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    thread_id = "t-auto"
    db.create_session(display_thread_id=thread_id, title="Agent")

    monkeypatch.setattr(
        "media2text.agent.thread_title.suggest_thread_title",
        lambda *_args, **_kwargs: "抖音监控配置",
    )
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    title = maybe_auto_title_thread(
        db,
        cfg,
        thread_id,
        user_text="怎么开启监控？",
        assistant_text="在左侧选择博主后点击监控。",
    )
    assert title == "抖音监控配置"
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    assert row["title"] == "抖音监控配置"
    conn.close()


def test_suggest_thread_title_falls_back_without_llm(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    title = suggest_thread_title(
        cfg,
        user_text="帮我总结昨晚直播",
        assistant_text="好的，正在整理要点。",
    )
    assert title == "帮我总结昨晚直播"
