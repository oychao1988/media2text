from media2text.core.config import AppConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.storage.repos import (
    CreatorRepo,
    DesktopEventRepo,
    LiveSessionRepo,
    PipelineEventRepo,
)


def test_set_offline_since_dual_writes_obs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsw1",
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
    iso = "2026-06-09T12:00:00+00:00"
    sw.set_offline_since(sid, iso, creator_id=cid)
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.offline_since_at == iso
    assert row.obs_still_live == 0
    events = PipelineEventRepo(conn).list_for_session(sid)
    assert any(e.status == "offline_pending" for e in events)


def test_clear_offline_since_restores_obs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsw2",
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
    iso = "2026-06-09T12:00:00+00:00"
    sw.set_offline_since(sid, iso, creator_id=cid)
    sw.clear_offline_since(sid, creator_id=cid)
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.offline_since_at is None
    assert row.obs_still_live == 1


def test_offline_since_atomic(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsw4",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=99999,
    )

    def fail_repo_set_offline(*_args, **_kwargs) -> None:
        raise AssertionError("set_offline_since must not call LiveSessionRepo")

    def fail_pipeline_insert(*_args, **_kwargs) -> str:
        raise AssertionError("PipelineEventRepo.insert must not be called")

    def fail_desktop_enqueue(*_args, **_kwargs) -> str:
        raise AssertionError("DesktopEventRepo.enqueue_creator_updated must not be called")

    monkeypatch.setattr(LiveSessionRepo, "set_offline_since", fail_repo_set_offline)
    monkeypatch.setattr(PipelineEventRepo, "insert", fail_pipeline_insert)
    monkeypatch.setattr(
        DesktopEventRepo, "enqueue_creator_updated", fail_desktop_enqueue
    )

    sw = StateWriter(conn, cfg=cfg)
    iso = "2026-06-09T12:00:00+00:00"
    sw.set_offline_since(sid, iso, creator_id=cid)

    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.offline_since_at == iso
    assert row.obs_still_live == 0
    events = PipelineEventRepo(conn).list_for_session(sid)
    assert any(e.status == "offline_pending" for e in events)
    desktop = DesktopEventRepo(conn).claim_pending(limit=10)
    assert any(e.creator_id == cid for e in desktop)


def test_write_obs_updates_columns(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsw3",
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
    sw.write_obs(sid, ffmpeg_alive=True, stt_alive=False, still_live=True)
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.obs_ffmpeg_alive == 1
    assert row.obs_stt_alive == 0
    assert row.obs_still_live == 1
    assert row.obs_polled_at is not None
