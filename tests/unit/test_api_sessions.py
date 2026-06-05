import json

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.status import build_live_status
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_creator_sessions(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_list",
        profile_url="https://www.douyin.com/user/sec_list",
        platform="douyin",
        monitor_enabled=True,
    )
    live_dir = workspace / "creators" / "sec_list" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T100000Z.flv"
    flv.write_bytes(b"x")
    partial = flv.with_suffix(".transcript.partial.json")
    partial.write_text(
        json.dumps({"text": "t", "segments": []}),
        encoding="utf-8",
    )
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(flv),
    )
    manifest = {
        "platform": "douyin",
        "sec_uid": "sec_list",
        "live": [],
        "live_groups": [{"date": "2026-06-04", "summary_path": "x", "session_ids": []}],
    }
    (workspace / "creators" / "sec_list" / "agent-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    conn.close()
    return cid


def test_list_sessions_and_manifest(api_client, workspace) -> None:
    cid = _seed_creator_sessions(workspace)
    r = api_client.get(f"/api/creators/{cid}/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["sessions"]) >= 1
    assert body["sessions"][0]["has_transcript"] is True
    assert body["live_groups"]

    mf = api_client.get(f"/api/creators/{cid}/manifest")
    assert mf.status_code == 200
    assert mf.json()["manifest"]["sec_uid"] == "sec_list"


def test_sessions_filter_has_transcript(api_client, workspace) -> None:
    cid = _seed_creator_sessions(workspace)
    r = api_client.get(f"/api/creators/{cid}/sessions?has_transcript=true")
    assert all(s["has_transcript"] for s in r.json()["sessions"])
    r2 = api_client.get(f"/api/creators/{cid}/sessions?has_transcript=false")
    assert r2.status_code == 200
    assert r2.json()["sessions"] == []


def test_live_status(api_client, workspace) -> None:
    r = api_client.get("/api/live/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "active_recordings" in body
    assert "post_process" in body
    assert body["command"] == "api live status"


def test_build_live_status_shape(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    payload = build_live_status(cfg, conn)
    conn.close()
    assert payload["daemon_lock_pid"] is None
    assert isinstance(payload["active_recordings"], list)


def test_manifest_not_found(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_nom",
        profile_url="https://www.douyin.com/user/sec_nom",
        platform="douyin",
    )
    conn.close()
    r = api_client.get(f"/api/creators/{cid}/manifest")
    assert r.status_code == 404


def test_session_summary_empty_when_missing(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_sum_empty",
        profile_url="https://example.com",
        platform="douyin",
    )
    flv = workspace / "creators" / "sec_sum_empty" / "live" / "x.flv"
    flv.parent.mkdir(parents=True)
    flv.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(flv),
    )
    LiveSessionRepo(conn).update_status(sid, local_path=str(flv), status="completed")
    conn.close()

    r = api_client.get(f"/api/sessions/{sid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["text"] == ""
