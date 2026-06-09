import time
from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.live.segment_watcher import SegmentWatcher
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _seed_hls_session(conn, tmp_path: Path) -> tuple[str, Path]:
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAwatcher",
        profile_url="https://x",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAwatcher/live/20260609T120000Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    return sid, session_dir


def test_watcher_closes_stable_segment_and_enqueues_job(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.live.segment_pipeline.stable_mtime_sec = 0.1
    conn = open_db(cfg)
    sid, session_dir = _seed_hls_session(conn, tmp_path)
    part_path = session_dir / "parts/seg-00001.m4s"
    part_path.write_bytes(b"x" * 128)

    repo = SegmentManifestRepo(conn)
    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="recording",
    )

    import threading

    stop = threading.Event()
    watcher = SegmentWatcher(cfg, stop=stop)
    watcher.tick_once(conn)
    time.sleep(0.15)
    watcher.tick_once(conn)

    assert SegmentProcessJobRepo(conn).has_pending(sid, part_index=1)
    row = repo.get_part(sid, 1)
    assert row is not None
    assert row.state == "closed"


def test_watcher_skips_growing_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.live.segment_pipeline.stable_mtime_sec = 0.2
    conn = open_db(cfg)
    sid, session_dir = _seed_hls_session(conn, tmp_path)
    part_path = session_dir / "parts/seg-00001.m4s"
    part_path.write_bytes(b"a" * 64)

    repo = SegmentManifestRepo(conn)
    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="recording",
    )

    import threading

    stop = threading.Event()
    watcher = SegmentWatcher(cfg, stop=stop)
    watcher.tick_once(conn)
    part_path.write_bytes(b"a" * 128)
    watcher.tick_once(conn)

    assert not SegmentProcessJobRepo(conn).has_pending(sid, part_index=1)


def test_force_close_session_enqueues_last_part(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sid, session_dir = _seed_hls_session(conn, tmp_path)
    part_path = session_dir / "parts/seg-00002.m4s"
    part_path.write_bytes(b"part")

    repo = SegmentManifestRepo(conn)
    repo.upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="recording",
    )

    import threading

    stop = threading.Event()
    watcher = SegmentWatcher(cfg, stop=stop)
    watcher.force_close_session(conn, sid, session_dir)

    assert SegmentProcessJobRepo(conn).has_pending(sid, part_index=2)
    row = repo.get_part(sid, 2)
    assert row is not None
    assert row.state == "closed"
