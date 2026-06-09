from media2text.core.config import AppConfig
from media2text.core.live.hls_recorder import mark_closed_with_duration
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _session(conn) -> str:
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAApartDur",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    return LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path="/tmp/x.flv",
    )


def test_close_part_writes_duration_and_export_discontinuity(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sid = _session(conn)
    repo = SegmentManifestRepo(conn)
    session_dir = tmp_path / "data/creators/x/live/anchor"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    (parts_dir / "seg-00001.m4s").write_bytes(b"x" * 10)
    (session_dir / "master.m3u8").write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXTINF:118.5,",
                "parts/seg-00001.m4s",
                "#EXT-X-DISCONTINUITY",
                "#EXTINF:30.0,",
                "parts/seg-00002.m4s",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="recording",
    )
    mark_closed_with_duration(repo, sid, 1, session_dir, bytes=10)

    repo.upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="recording",
        discontinuity_seq=1,
    )
    mark_closed_with_duration(repo, sid, 2, session_dir, bytes=10)

    payload = repo.export_json(sid, session_dir=session_dir)
    assert payload["discontinuity_at"] == [118.5]
    assert payload["parts"][0]["duration_sec"] == 118.5
    assert payload["parts"][1]["duration_sec"] == 30.0
