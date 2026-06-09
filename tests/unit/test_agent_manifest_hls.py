import json

from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_manifest_hls_session_playback_mode_and_parts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "data"
    ws.mkdir()
    from media2text.core.storage.db import connect

    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAhlsmanifest"
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    session_dir = ws / "creators" / sec_uid / "live/20260609T120000Z"
    session_dir.mkdir(parents=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    transcript = master.with_suffix(".transcript.json")
    transcript.write_text('{"text": "hi"}', encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        ffmpeg_pid=None,
        pipeline_mode="streaming",
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(master),
        ended=True,
    )
    parts_repo = SegmentManifestRepo(conn)
    parts_repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="uploaded",
    )
    parts_repo.mark_uploaded(
        sid,
        1,
        cloud_path="media2text/douyin/nick/live/20260609T120000Z/parts/seg-00001.m4s",
    )
    parts_repo.upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="closed",
    )

    out = refresh_manifest(conn, sec_uid=sec_uid, workspace=ws)
    payload = json.loads(out.read_text(encoding="utf-8"))
    live_item = next(i for i in payload["items"] if i["type"] == "live")

    assert live_item["playback_mode"] == "hls"
    assert live_item["parts"] == [
        {
            "index": 1,
            "state": "uploaded",
            "cloud_path": "media2text/douyin/nick/live/20260609T120000Z/parts/seg-00001.m4s",
        },
        {"index": 2, "state": "closed"},
    ]


def test_manifest_flv_session_playback_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "data"
    ws.mkdir()
    from media2text.core.storage.db import connect

    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAflvmanifest"
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T120000Z.flv"
    flv.write_bytes(b"x" * 32)

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=None,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(flv),
        ended=True,
    )

    out = refresh_manifest(conn, sec_uid=sec_uid, workspace=ws)
    payload = json.loads(out.read_text(encoding="utf-8"))
    live_item = payload["live"][0]

    assert live_item["playback_mode"] == "flv"
    assert "parts" not in live_item
