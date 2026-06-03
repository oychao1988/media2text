from media2text.core.storage.db import connect


def test_live_sessions_v3_columns(tmp_path) -> None:
    conn = connect(tmp_path / "data" / "media2text.db")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    assert "first_seen_live_at" in cols
    assert "recording_started_at" in cols
    assert "offline_since_at" in cols
    assert "platform_live_started_at" in cols
