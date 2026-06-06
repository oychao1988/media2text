import json

import pytest

from media2text.core.storage.db import _migrate_hermes_v1, connect
from media2text.core.storage.repos import CreatorRepo, DesktopChatRepo, LiveSnapshotRepo

pytestmark = pytest.mark.desktop


def test_desktop_v1_tables_exist(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "creator_live_snapshots" in tables
    assert "sessions" in tables
    assert "messages" in tables
    assert "_legacy_desktop_chat_threads" in tables
    assert "desktop_chat_threads" not in tables
    cols = {r[1] for r in conn.execute("PRAGMA table_info(creators)").fetchall()}
    assert "auto_record_override" in cols
    session_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    assert "creator_id" in session_cols
    conn.close()


def test_auto_record_override_survives_reconnect(tmp_path) -> None:
    """Platform-unique migration must not reset auto_record_override on reconnect."""
    db = tmp_path / "media2text.db"
    conn = connect(db)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_persist",
        profile_url="https://example.com/u",
        platform="douyin",
    )
    CreatorRepo(conn).set_auto_record_override(cid, "on")
    conn.close()

    conn2 = connect(db)
    row = CreatorRepo(conn2).get(cid)
    assert row is not None
    assert row.auto_record_override == "on"
    conn2.close()


def test_live_snapshot_and_chat_crud(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    conn.execute(
        """
        INSERT INTO creators (
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, created_at
        )
        VALUES ('c1', 'douyin', 's1', 't', 'https://example.com/u', 0, 1, '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()

    snaps = LiveSnapshotRepo(conn)
    snaps.upsert("c1", is_live=True, room_id="99", title="live")
    row = snaps.get("c1")
    assert row is not None
    assert row.is_live == 1
    assert row.room_id == "99"

    chat = DesktopChatRepo(conn)
    tid = chat.create_thread(creator_id="c1", title="thread")
    chat.add_message(tid, role="user", content="hello")
    msgs = chat.list_messages(tid)
    assert len(msgs) == 1
    assert msgs[0].content == "hello"
    conn.close()


def test_hermes_migration_preserves_chat_rows(tmp_path) -> None:
    import sqlite3

    from media2text.core.storage.db import SCHEMA, _migrate_creators, _migrate_desktop_v1

    db_path = tmp_path / "legacy.db"
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    conn2.executescript(SCHEMA)
    _migrate_creators(conn2)
    _migrate_desktop_v1(conn2)
    conn2.execute(
        """
        INSERT INTO creators (
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, created_at
        )
        VALUES ('c1', 'douyin', 's1', 't', 'https://example.com/u', 0, 1, '2026-01-01T00:00:00Z')
        """
    )
    conn2.execute(
        """
        INSERT INTO desktop_chat_threads (
          id, creator_id, session_id, title, provider_name, model,
          context_mode, created_at, updated_at
        )
        VALUES ('t1', 'c1', NULL, 'legacy', 'openai', 'auto', 'both',
                '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')
        """
    )
    conn2.execute(
        """
        INSERT INTO desktop_chat_messages (
          id, thread_id, role, content, thinking_text, duration_ms, created_at
        )
        VALUES ('m1', 't1', 'user', 'legacy-msg', NULL, NULL, '2026-01-02T00:00:01Z')
        """
    )
    conn2.commit()
    _migrate_hermes_v1(conn2)

    session_count = conn2.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    message_count = conn2.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert session_count == 1
    assert message_count == 1

    row = conn2.execute("SELECT creator_id FROM sessions WHERE id = 't1'").fetchone()
    assert row["creator_id"] == "c1"

    nullable = conn2.execute(
        """
        INSERT INTO sessions (
          id, display_thread_id, parent_session_id, title, creator_id,
          active_binding_json, token_estimate, created_at, updated_at
        )
        VALUES ('s-null', 'display-null', NULL, NULL, NULL, ?, 0, 't', 't')
        """,
        (json.dumps({"model": "auto", "context_mode": "both"}),),
    )
    assert nullable.rowcount == 1
    conn2.commit()
    conn2.close()


def test_desktop_v2_tables_and_probe_error(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "desktop_events" in tables
    cols = {
        r[1]
        for r in conn.execute("PRAGMA table_info(creator_live_snapshots)").fetchall()
    }
    assert "probe_error" in cols
    conn.close()
