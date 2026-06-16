from datetime import datetime, timedelta, timezone

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.session_recovery import recover_orphan_sessions
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_recover_orphan_sessions_enqueues_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"offline_confirm_sec": 45})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAorphan",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute("UPDATE live_sessions SET obs_still_live = 0 WHERE id = ?", (sid,))
    conn.commit()

    count = recover_orphan_sessions(cfg, conn)
    assert count >= 1
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")


def test_recover_orphan_sessions_marks_very_old_without_offline(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAold",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn.execute(
        "UPDATE live_sessions SET started_at = ?, obs_ffmpeg_alive = 0 WHERE id = ?",
        (old, sid),
    )
    conn.commit()

    recover_orphan_sessions(cfg, conn)
    row = LiveSessionRepo(conn).get(sid)
    assert row.status == "failed"
    assert row.error == "stale_recording"
