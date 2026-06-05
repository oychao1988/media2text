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
    assert session["kind"] == "live"
    assert session["item_id"] == sid
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


def test_list_sessions_gallery_directory_media_available(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_gallery",
        profile_url="https://www.douyin.com/user/sec_gallery",
        platform="douyin",
    )
    gallery_dir = workspace / "creators" / "sec_gallery" / "images" / "7609968774381490533"
    gallery_dir.mkdir(parents=True)
    (gallery_dir / "01.jpeg").write_bytes(b"jpeg")
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, local_path, updated_at)
        VALUES ('7609968774381490533', ?, '图文作品', 1, 'gallery', 'downloaded', ?, datetime('now'))
        """,
        (cid, str(gallery_dir)),
    )
    conn.commit()

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    vod = next(s for s in payload["sessions"] if s["kind"] == "vod")
    assert vod["media_path"] == "creators/sec_gallery/images/7609968774381490533"
    assert vod["media_available"] is True
    assert vod["media_type"] == "gallery"


def test_list_sessions_includes_listed_vod(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_listed",
        profile_url="https://www.douyin.com/user/sec_listed",
        platform="douyin",
    )
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, updated_at)
        VALUES ('pending1', ?, '待下载作品', 1, 'video', 'listed', datetime('now'))
        """,
        (cid,),
    )
    conn.commit()

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    vod = next(s for s in payload["sessions"] if s["kind"] == "vod")
    assert vod["status"] == "listed"
    assert vod["media_available"] is False
    assert vod["media_path"] is None
