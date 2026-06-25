import json

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.transcript_writer import (
    find_summary_sidecar,
    find_transcript_sidecar,
    resolve_summarize_paths,
)
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_hls_transcript_sidecar_uses_session_anchor(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    sec_uid = "MS4wLjABAAAAhls"
    live_dir = ws / "creators" / sec_uid / "live" / "20260611T110019Z"
    live_dir.mkdir(parents=True)
    master = live_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    transcript = live_dir / "20260611T110019Z.transcript.json"
    transcript.write_text(json.dumps({"text": "hi", "segments": []}), encoding="utf-8")

    rel_master = f"creators/{sec_uid}/live/20260611T110019Z/master.m3u8"
    rel_dir = f"creators/{sec_uid}/live/20260611T110019Z"
    assert find_transcript_sidecar(rel_master, workspace=ws) == transcript
    assert find_transcript_sidecar(rel_dir, workspace=ws) == transcript
    assert _transcript_sidecar_path(rel_master, workspace=ws) == str(
        transcript.relative_to(ws)
    )


def test_hls_summary_sidecar_uses_session_anchor(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    sec_uid = "MS4wLjABAAAAhls_sum"
    live_dir = ws / "creators" / sec_uid / "live" / "20260611T110019Z"
    live_dir.mkdir(parents=True)
    master = live_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    transcript = live_dir / "20260611T110019Z.transcript.json"
    transcript.write_text(json.dumps({"text": "hi", "segments": []}), encoding="utf-8")
    summary = live_dir / "20260611T110019Z.summary.md"
    summary.write_text("## Summary\n\nok", encoding="utf-8")

    rel_master = f"creators/{sec_uid}/live/20260611T110019Z/master.m3u8"
    assert find_summary_sidecar(rel_master, workspace=ws) == summary
    assert _summary_sidecar_path(rel_master, workspace=ws) == str(
        summary.relative_to(ws)
    )


def test_resolve_summarize_paths_for_hls_master(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    live_dir = ws / "creators/sec/live/20260622T065310Z"
    live_dir.mkdir(parents=True)
    master = live_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    transcript = live_dir / "20260622T065310Z.transcript.json"
    transcript.write_text(json.dumps({"text": "hello", "segments": []}), encoding="utf-8")

    resolved = resolve_summarize_paths(master, workspace=ws)
    assert resolved is not None
    write_media, transcript_path = resolved
    assert transcript_path == transcript
    assert write_media.name == "20260622T065310Z"


def test_sessions_list_marks_hls_transcript(api_client, workspace) -> None:
    sec_uid = "MS4wLjABAAAAhls_list"
    live_dir = workspace / "creators" / sec_uid / "live" / "20260611T120000Z"
    live_dir.mkdir(parents=True)
    master = live_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    transcript = live_dir / "20260611T120000Z.transcript.json"
    transcript.write_text(json.dumps({"text": "x", "segments": []}), encoding="utf-8")

    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://www.douyin.com/user/hls_list",
        platform="douyin",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(master),
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(live_dir),
        ended=True,
    )
    conn.close()

    r = api_client.get(f"/api/creators/{cid}/sessions")
    assert r.status_code == 200
    session = next(s for s in r.json()["sessions"] if s["session_id"] == sid)
    assert session["has_transcript"] is True
    assert session["transcript_path"] == str(
        transcript.relative_to(workspace)
    )

    hist = api_client.get(f"/api/creators/{cid}/history/live/{sid}/transcript")
    assert hist.status_code == 200
    assert hist.json()["text"] == "x"
