from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.probe_guard import ProbeExecutionGuard
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.state_writer import StateWriter
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo


def test_poll_active_writes_obs_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
        live=LiveConfig(min_recording_sec_before_offline_end=0),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAobs1",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )
    creator = CreatorRepo(conn).get(cid)
    assert creator is not None
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None

    enqueue = MagicMock()
    monkeypatch.setattr(MonitorTaskRepo, "enqueue", enqueue)

    core = MagicMock(spec=LiveRecordingCore)
    core._cfg = cfg
    core._conn = conn
    core._creators = CreatorRepo(conn)
    core._sessions = LiveSessionRepo(conn)
    core._platform = "douyin"
    core._streaming_legacy_finalize = set()
    core._stt_sessions = {}
    core._process_alive = MagicMock(return_value=True)
    core._use_streaming_pipeline = MagicMock(return_value=False)
    core._recording_still_live = MagicMock(return_value=True)
    core._adapter = MagicMock()

    real = LiveRecordingCore.__new__(LiveRecordingCore)
    real.poll_active_session = LiveRecordingCore.poll_active_session.__get__(core, LiveRecordingCore)

    state = StateWriter(conn, cfg=cfg)
    with patch(
        "media2text.core.live.recording.upsert_live_snapshot",
        return_value=False,
    ):
        real.poll_active_session(row, creator, state=state)

    enqueue.assert_not_called()
    updated = LiveSessionRepo(conn).get(sid)
    assert updated is not None
    assert updated.obs_polled_at is not None
    assert updated.obs_still_live == 1


def test_poll_active_recordings_delegates_when_reconciler_enabled(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAobs2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )

    enqueue = MagicMock()
    monkeypatch.setattr(MonitorTaskRepo, "enqueue", enqueue)

    core = MagicMock()
    core._cfg = cfg
    core._conn = conn
    core._sessions = LiveSessionRepo(conn)
    core._creators = CreatorRepo(conn)
    core._platform = "douyin"
    core.poll_active_session = MagicMock()
    finalized = LiveRecordingCore.poll_active_recordings.__get__(core, LiveRecordingCore)()
    assert finalized == []
    assert core.poll_active_session.called
    enqueue.assert_not_called()
