import json

import pytest

from media2text.api.services.sessions_list import list_creator_sessions
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_list_sessions_normalizes_paths_and_media_available(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_paths",
        profile_url="https://www.douyin.com/user/sec_paths",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_paths" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T100000Z.flv"
    flv.write_bytes(b"flv")
    summary = flv.with_suffix(".summary.md")
    summary.write_text("## 摘要\n\nok", encoding="utf-8")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(flv),
    )
    manifest = {
        "platform": "douyin",
        "sec_uid": "sec_paths",
        "live": [
            {
                "id": sid,
                "media_path": str(flv),
                "summary_path": str(summary),
            }
        ],
        "live_groups": [],
    }
    (workspace / "creators" / "sec_paths" / "agent-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    assert payload["ok"] is True
    session = payload["sessions"][0]
    assert session["media_path"] == "creators/sec_paths/live/20260604T100000Z.flv"
    assert session["media_available"] is True
    assert session["has_summary"] is True
    assert session["summary_path"] == "creators/sec_paths/live/20260604T100000Z.summary.md"


def test_list_sessions_media_missing(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_missing",
        profile_url="https://www.douyin.com/user/sec_missing",
        platform="douyin",
    )
    missing = workspace / "creators" / "sec_missing" / "live" / "gone.flv"
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(missing),
    )

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    session = payload["sessions"][0]
    assert session["media_path"] == "creators/sec_missing/live/gone.flv"
    assert session["media_available"] is False
