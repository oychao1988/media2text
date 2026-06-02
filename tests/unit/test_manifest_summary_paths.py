import json
from pathlib import Path

from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_manifest_includes_summary_path_and_live_groups(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "data"
    ws.mkdir()
    from media2text.core.storage.db import connect

    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAsummary"
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    mp4 = live_dir / "20260601T130643Z.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    per_file_summary = mp4.with_suffix(".summary.md")
    per_file_summary.write_text("summary", encoding="utf-8")
    merged = live_dir / "20260601_merged.summary.md"
    merged.write_text("merged", encoding="utf-8")
    live_dir.joinpath("20260601_merged.summary.json").write_text(
        json.dumps(
            {
                "merged": True,
                "sources": [{"session_id": "sid-a"}, {"session_id": "sid-b"}],
            }
        ),
        encoding="utf-8",
    )

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
    live_item = payload["live"][0]
    assert live_item["summary_path"] == str(per_file_summary)
    assert payload["live_groups"][0]["summary_path"] == str(merged)
    assert payload["live_groups"][0]["session_ids"] == ["sid-a", "sid-b"]
