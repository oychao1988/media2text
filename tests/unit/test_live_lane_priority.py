from media2text.core.config import AppConfig
from media2text.core.live.live_lane import live_lane_needs_priority
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
)


def test_live_lane_true_when_live_snapshot_without_session(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAliveprio",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(
        creator_id=cid,
        is_live=True,
        room_id="123",
        title="live",
    )
    assert live_lane_needs_priority(conn, cfg) is True


def test_live_lane_true_when_prepare_task_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAprepare",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="prepare_live_recording",
        dedupe_key=f"prepare:{cid}",
        priority=1,
    )
    assert live_lane_needs_priority(conn, cfg) is True


def test_live_lane_false_when_recording_active(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAArecording",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(
        creator_id=cid,
        is_live=True,
        room_id="123",
        title="live",
    )
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="123",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=1,
    )
    assert live_lane_needs_priority(conn, cfg) is False
