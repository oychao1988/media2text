import json
from unittest.mock import patch

from media2text.core.config import AppConfig, NotifyConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.outbox import NotifyDaemonGuard, NotifyEventRepo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_notify_event_repo_enqueue_claim_mark_done(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    repo = NotifyEventRepo(conn)
    event_id = repo.enqueue(
        kind=EventKind.LIVE_ENDED.value,
        title="博主",
        body="下播",
        creator_id="c1",
        session_id="s1",
        dedupe_key="live_ended:s1",
    )
    assert repo.count_pending() == 1
    pending = repo.claim_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].id == event_id
    payload = json.loads(pending[0].payload_json)
    assert payload["title"] == "博主"
    repo.mark_done(event_id)
    assert repo.count_pending() == 0
    assert repo.claim_pending(limit=10) == []


def test_notify_outbox_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsw5",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )
    sw = StateWriter(conn, cfg=cfg)

    def fail_emit(*_args, **_kwargs) -> None:
        raise AssertionError("sync emit must not run for set_offline_since")

    monkeypatch.setattr(NotifyService, "emit", fail_emit)
    sw.set_offline_since(sid, "2026-06-09T12:00:00+00:00", creator_id=cid)

    repo = NotifyEventRepo(conn)
    assert repo.count_pending() >= 1
    row = repo.claim_pending(limit=1)[0]
    assert row.kind == EventKind.LIVE_ENDED.value
    assert row.session_id == sid
    assert row.creator_id == cid


def test_notify_outbox_only_blocks_daemon_sync_emit(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False, outbox_only=True),
    )
    svc = NotifyService(cfg)
    NotifyDaemonGuard.enter()
    with (
        patch("media2text.core.notify.service.play_sound") as mock_sound,
        patch("media2text.core.notify.service.send_feishu_text") as mock_feishu,
    ):
        svc.emit(NotifyEvent(kind=EventKind.LIVE_ENDED, title="t", body="b"))
    mock_sound.assert_not_called()
    mock_feishu.assert_not_called()


def test_notify_drain_emits_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False),
    )
    from media2text.api.services.notify_event_drain import drain_once
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    NotifyEventRepo(conn).enqueue(
        kind=EventKind.RECORDING_COMPLETED.value,
        title="博主",
        body="录制完成",
    )
    conn.close()

    with patch("media2text.api.services.notify_event_drain.NotifyService.emit") as mock_emit:
        n = drain_once(cfg)
    assert n == 1
    mock_emit.assert_called_once()
    assert mock_emit.call_args.args[0].kind == EventKind.RECORDING_COMPLETED
