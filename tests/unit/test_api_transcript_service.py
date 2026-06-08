import json

import pytest
from fastapi import HTTPException

from media2text.api.services.transcript import read_transcript_payload, read_summary_text
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_session(workspace, *, with_partial: bool = True) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_t",
        profile_url="https://www.douyin.com/user/sec_t",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_t" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T120000Z.flv"
    flv.write_bytes(b"\x00")
    if with_partial:
        partial = flv.with_suffix(".transcript.partial.json")
        partial.write_text(
            json.dumps(
                {
                    "partial": True,
                    "text": "hello",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
                }
            ),
            encoding="utf-8",
        )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="room1",
        temp_path=str(flv),
    )
    conn.close()
    return sid


def test_get_session_and_transcript(api_client, workspace) -> None:
    sid = _seed_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["session"]["session_id"] == sid
    assert body["session"]["paths"]["media_path"].endswith(".flv")

    tr = api_client.get(f"/api/sessions/{sid}/transcript")
    assert tr.status_code == 200
    t = tr.json()
    assert t["partial"] is True
    assert t["text"] == "hello"
    assert len(t["segments"]) == 1


def test_transcript_after_ffmpeg_reconnect(api_client, workspace) -> None:
    """Partial sidecar stays on anchor FLV; temp_path moves to _rN segment."""
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_reconnect",
        profile_url="https://www.douyin.com/user/sec_reconnect",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_reconnect" / "live"
    live_dir.mkdir(parents=True)
    anchor = live_dir / "20260608T045208Z.flv"
    anchor.write_bytes(b"\x00")
    reconnect = live_dir / "20260608T062751Z_r1.flv"
    reconnect.write_bytes(b"\x00")
    partial = anchor.with_suffix(".transcript.partial.json")
    partial.write_text(
        json.dumps(
            {
                "text": "live partial",
                "segments": [{"start": 10.0, "end": 12.0, "text": "live partial"}],
            }
        ),
        encoding="utf-8",
    )
    sessions = LiveSessionRepo(conn)
    sid = sessions.create(
        creator_id=cid,
        room_id="room1",
        temp_path=str(reconnect),
    )
    conn.execute(
        "UPDATE live_sessions SET segment_paths_json = ? WHERE id = ?",
        (json.dumps([str(anchor)]), sid),
    )
    conn.commit()
    conn.close()

    tr = api_client.get(f"/api/sessions/{sid}/transcript")
    assert tr.status_code == 200
    body = tr.json()
    assert body["partial"] is True
    assert body["text"] == "live partial"

    detail = api_client.get(f"/api/sessions/{sid}").json()["session"]
    assert detail["paths"]["partial_transcript_path"] is not None


def test_transcript_not_found(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_empty",
        profile_url="https://www.douyin.com/user/sec_empty",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(workspace / "creators/sec_empty/live/x.flv"),
    )
    conn.close()
    r = api_client.get(f"/api/sessions/{sid}/transcript")
    assert r.status_code == 404


def test_read_transcript_final_md(tmp_path) -> None:
    media = tmp_path / "live" / "a.flv"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    md = media.with_suffix(".transcript.md")
    md.write_text("# transcript\n\nline one", encoding="utf-8")
    payload = read_transcript_payload(media)
    assert payload["partial"] is False
    assert "line one" in payload["text"]


def test_read_summary(tmp_path) -> None:
    media = tmp_path / "live" / "a.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    summary = media.with_suffix(".summary.md")
    summary.write_text("## Summary\n\nok", encoding="utf-8")
    text = read_summary_text(media)
    assert "Summary" in text

    with pytest.raises(HTTPException) as exc:
        read_summary_text(tmp_path / "missing.mp4")
    assert exc.value.status_code == 404
