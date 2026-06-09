from unittest.mock import MagicMock

from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.live.segment_process import run_segment_process_job
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def test_segment_process_deletes_local_only_after_upload_confirmed(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.aliyundrive.enabled = True
    cfg.live.segment_pipeline.upload.delete_local_after_upload = True
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegproc",
        profile_url="https://x",
        display_name="tester",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAsegproc/live/anchor"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    part_path = parts_dir / "seg-00001.m4s"
    part_path.write_bytes(b"segment-data")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(session_dir / "master.m3u8"),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    parts_repo = SegmentManifestRepo(conn)
    parts_repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
    )
    job_id = SegmentProcessJobRepo(conn).enqueue(session_id=sid, part_index=1)
    assert job_id

    monkeypatch.setattr(
        "media2text.core.live.segment_process.upload_live_part",
        lambda *a, **k: {"ok": True, "cloud_path": "media2text/douyin/tester/live/anchor/parts/seg-00001.m4s"},
    )

    notify = MagicMock()
    result = run_segment_process_job(cfg, conn, job_id=job_id, notify=notify)

    assert result["ok"] is True
    assert not part_path.exists()
    row = parts_repo.get_part(sid, 1)
    assert row is not None
    assert row.state == "local_deleted"


def test_segment_process_keeps_local_on_upload_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.aliyundrive.enabled = True
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegfail",
        profile_url="https://x",
        display_name="tester",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAsegfail/live/anchor"
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
        lambda *a, **k: {"ok": False, "error": "upload_failed"},
    )

    result = run_segment_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert result["ok"] is False
    assert part_path.exists()
