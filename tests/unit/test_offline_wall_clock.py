from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, NotifyConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.notify import NotifyService
from media2text.core.notify.events import EventKind
from media2text.core.notify.outbox import NotifyDaemonGuard
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _pending_live_ended_count(conn, session_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM notify_events
        WHERE session_id = ? AND kind = ? AND delivered_at IS NULL
        """,
        (session_id, EventKind.LIVE_ENDED.value),
    ).fetchone()
    return int(row["c"]) if row else 0


def _core(tmp_path, monkeypatch, *, confirm_sec: int = 45) -> tuple:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False, outbox_only=True),
    )
    cfg.live.offline_confirm_sec = confirm_sec
    cfg.live.offline_trust_recording_signals = False
    NotifyDaemonGuard.enter()
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAwall",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAwall/live/x.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    conn.execute("UPDATE live_sessions SET started_at = ? WHERE id = ?", (old, sid))
    conn.commit()

    adapter = MagicMock()
    adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="99", is_live=False, stream_flv_url=None
    )
    notify = NotifyService(cfg)
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform="douyin",
        processes={},
        notify=notify,
    )
    return cfg, conn, creators, sessions, core, sid, notify


def test_first_offline_emits_live_ended_without_finalize(tmp_path, monkeypatch) -> None:
    cfg, conn, _, sessions, core, sid, notify = _core(tmp_path, monkeypatch)

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=False),
    ):
        core.poll_active_recordings()

    row = sessions.get(sid)
    assert row is not None
    assert row.offline_since_at is not None
    assert _pending_live_ended_count(conn, sid) == 1


def test_finalize_after_offline_confirm_sec(tmp_path, monkeypatch) -> None:
    from media2text.core.live.task_reconciler import reconcile_live
    from media2text.core.storage.repos import MonitorTaskRepo

    cfg, conn, _, _sessions, core, sid, notify = _core(
        tmp_path, monkeypatch, confirm_sec=10
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
    conn.execute(
        "UPDATE live_sessions SET offline_since_at = ?, obs_still_live = 0 WHERE id = ?",
        (past, sid),
    )
    conn.commit()

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=False),
    ):
        core.poll_active_recordings()
        reconcile_live(cfg, conn)

    tasks = MonitorTaskRepo(conn).count_by_status()
    assert tasks.get("pending", 0) == 1
    row = conn.execute(
        "SELECT task_type FROM monitor_tasks WHERE status = 'pending' LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["task_type"] == "finalize"


def test_live_resume_clears_offline_since(tmp_path, monkeypatch) -> None:
    _, conn, _, sessions, core, sid, _notify = _core(tmp_path, monkeypatch)
    iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE live_sessions SET offline_since_at = ? WHERE id = ?",
        (iso, sid),
    )
    conn.commit()
    core._adapter.get_live_room.return_value = LiveRoomInfo(
        room_id="99", is_live=True, stream_flv_url="https://example.com/x.flv"
    )

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=True),
    ):
        core.poll_active_recordings()

    row = sessions.get(sid)
    assert row is not None
    assert row.offline_since_at is None


def test_live_ended_emitted_only_once(tmp_path, monkeypatch) -> None:
    _, conn, _, sessions, core, sid, notify = _core(tmp_path, monkeypatch)

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=False),
    ):
        core.poll_active_recordings()
        core.poll_active_recordings()

    assert _pending_live_ended_count(conn, sid) == 1
    row = sessions.get(sid)
    assert row is not None
    assert row.offline_since_at is not None
