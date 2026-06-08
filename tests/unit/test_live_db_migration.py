from media2text.core.storage.db import connect


def test_live_sessions_obs_columns(tmp_path) -> None:
    conn = connect(tmp_path / "data" / "media2text.db")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    assert {"obs_ffmpeg_alive", "obs_stt_alive", "obs_still_live", "obs_polled_at"} <= cols
