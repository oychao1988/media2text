from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _session(conn) -> str:
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAApart",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    return LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path="/tmp/x.flv",
    )


def test_live_session_part_state_transitions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sid = _session(conn)
    repo = SegmentManifestRepo(conn)

    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="recording",
    )
    repo.mark_closed(sid, 1, bytes=1024)
    row = repo.get_part(sid, 1)
    assert row is not None
    assert row.state == "closed"
    assert row.bytes == 1024


def test_export_json_writes_session_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sid = _session(conn)
    repo = SegmentManifestRepo(conn)
    session_dir = tmp_path / "data/creators/x/live/anchor"
    session_dir.mkdir(parents=True)

    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
        duration_sec=120.0,
    )
    repo.upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="recording",
        discontinuity_seq=1,
    )
    payload = repo.export_json(sid, session_dir=session_dir)
    assert payload["media_format"] == "hls"
    assert len(payload["parts"]) == 2
    assert payload["discontinuity_at"] == [120.0]
    assert (session_dir / "session.manifest.json").is_file()


def test_mark_uploaded_and_local_deleted(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sid = _session(conn)
    repo = SegmentManifestRepo(conn)
    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
    )
    repo.mark_uploaded(sid, 1, cloud_path="media2text/douyin/x/live/parts/seg-00001.m4s")
    repo.mark_local_deleted(sid, 1)
    row = repo.get_part(sid, 1)
    assert row is not None
    assert row.state == "local_deleted"
    assert row.cloud_path is not None
