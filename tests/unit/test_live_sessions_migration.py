from media2text.core.storage.db import connect


def test_live_sessions_v3_columns(tmp_path) -> None:
    conn = connect(tmp_path / "data" / "media2text.db")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    assert "first_seen_live_at" in cols
    assert "recording_started_at" in cols
    assert "offline_since_at" in cols
    assert "platform_live_started_at" in cols


def test_live_sessions_v4_pipeline_mode_backfill(tmp_path) -> None:
    db_path = tmp_path / "data" / "media2text.db"
    conn = connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    assert "pipeline_mode" in cols

    conn.execute(
        """
        INSERT INTO creators
          (id, platform, sec_uid, watch_live, monitor_enabled, created_at)
        VALUES ('c1', 'douyin', 'MS4wLjABAAAAtest', 0, 1, '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO live_sessions
          (id, creator_id, room_id, started_at, temp_path, status, pipeline_mode)
        VALUES ('legacy-row', 'c1', '1', '2026-01-01T00:00:00+00:00', '/x.flv', 'completed', NULL)
        """
    )
    conn.commit()

    from media2text.core.storage.db import _migrate_live_sessions_v4

    _migrate_live_sessions_v4(conn)
    row = conn.execute(
        "SELECT pipeline_mode FROM live_sessions WHERE id = 'legacy-row'"
    ).fetchone()
    assert row is not None
    assert row["pipeline_mode"] == "legacy"
