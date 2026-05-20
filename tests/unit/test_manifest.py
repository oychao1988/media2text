import json

from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_refresh_manifest_live_transcript_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "data"
    ws.mkdir()
    from media2text.core.storage.db import connect

    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAmanifest"
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    mp4 = live_dir / "20260520T000000Z.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    transcript = mp4.with_suffix(".transcript.json")
    transcript.write_text('{"text": "hi"}', encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(live_dir / "x.flv"),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(mp4),
        ended=True,
    )

    out = refresh_manifest(conn, sec_uid=sec_uid, workspace=ws)
    payload = json.loads(out.read_text(encoding="utf-8"))
    live_item = next(i for i in payload["items"] if i["type"] == "live")
    assert live_item["media_path"] == str(mp4)
    assert live_item["transcript_path"] == str(transcript)
