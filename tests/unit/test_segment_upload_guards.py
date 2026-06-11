from unittest.mock import MagicMock

from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.live.segment_process import run_segment_process_job
from media2text.core.live.segment_watcher import enqueue_closed_hls_part
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def test_segment_process_keeps_local_when_cloud_file_id_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.aliyundrive.enabled = True
    cfg.live.segment_pipeline.upload.delete_local_after_upload = True
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegverify",
        profile_url="https://x",
        display_name="tester",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAsegverify/live/anchor"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    part_path = parts_dir / "seg-00001.m4s"
    part_path.write_bytes(b"segment-data")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(session_dir / "master.m3u8"),
        session_dir=str(session_dir),
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
    )
    job_id = SegmentProcessJobRepo(conn).enqueue(session_id=sid, part_index=1)
    assert job_id

    monkeypatch.setattr(
        "media2text.core.live.segment_process.upload_live_part",
        lambda *a, **k: {"ok": True, "cloud_path": "media2text/x/parts/seg-00001.m4s"},
    )

    result = run_segment_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert result["ok"] is False
    assert result["error"] == "upload_unverified"
    assert part_path.exists()


def test_close_hls_part_enqueues_upload_job(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegclose",
        profile_url="https://x",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAsegclose/live/anchor"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    (parts_dir / "seg-00002.m4s").write_bytes(b"data")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(session_dir / "master.m3u8"),
        session_dir=str(session_dir),
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="recording",
    )

    job_id = enqueue_closed_hls_part(
        conn, session_id=sid, session_dir=session_dir, part_index=2
    )
    assert job_id
    row = SegmentManifestRepo(conn).get_part(sid, 2)
    assert row is not None
    assert row.state == "closed"
