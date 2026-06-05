from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo, DesktopChatRepo, LiveSnapshotRepo


def test_desktop_v1_tables_exist(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "creator_live_snapshots" in tables
    assert "desktop_chat_threads" in tables
    assert "desktop_chat_messages" in tables
    cols = {r[1] for r in conn.execute("PRAGMA table_info(creators)").fetchall()}
    assert "auto_record_override" in cols
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
