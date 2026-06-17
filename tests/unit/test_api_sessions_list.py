import json

import pytest

from media2text.api.services.sessions_list import list_creator_session_cloud, list_creator_sessions
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
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


def test_list_sessions_live_display_label(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_label",
        profile_url="https://www.douyin.com/user/sec_label",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_label" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260602T130400Z.flv"
    flv.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(flv),
    )
    conn.execute(
        "UPDATE live_sessions SET started_at = ? WHERE id = ?",
        ("2026-06-02T13:04:00+00:00", sid),
    )
    conn.commit()
    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()
    live = next(s for s in payload["sessions"] if s["item_id"] == sid)
    assert live["display_label"]
    assert "直播" in live["display_label"]


def test_list_sessions_include_cloud_false(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_no_cloud",
        profile_url="https://www.douyin.com/user/sec_no_cloud",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_no_cloud" / "live" / "x.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="x.mp4",
        file_kind="mp4",
        local_path=str(mp4),
        size=1,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="fid-1",
        cloud_relative_path="media2text/douyin/sec_no_cloud/live/x.mp4",
    )

    without = list_creator_sessions(
        conn, workspace=workspace, creator_id=cid, include_cloud=False
    )
    cloud = list_creator_session_cloud(conn, workspace=workspace, creator_id=cid)
    conn.close()

    assert without["sessions"][0]["cloud_available"] is False
    assert without["sessions"][0]["cloud_file_id"] is None
    assert cloud["items"][f"live:{sid}"]["cloud_available"] is True
    assert cloud["items"][f"live:{sid}"]["cloud_file_id"] == "fid-1"


def test_list_session_cloud_filters_keys(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_cloud_keys",
        profile_url="https://www.douyin.com/user/sec_cloud_keys",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_cloud_keys" / "live" / "x.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="x.mp4",
        file_kind="mp4",
        local_path=str(mp4),
        size=1,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="fid-1",
        cloud_relative_path="media2text/douyin/sec_cloud_keys/live/x.mp4",
    )

    payload = list_creator_session_cloud(
        conn,
        workspace=workspace,
        creator_id=cid,
        keys={"live:missing"},
    )
    conn.close()

    assert payload["items"] == {}


def test_list_sessions_fast_path_paginates_without_full_scan(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_fast",
        profile_url="https://www.douyin.com/user/sec_fast",
        platform="douyin",
    )
    for i in range(120):
        conn.execute(
            """
            INSERT INTO live_sessions
              (id, creator_id, room_id, started_at, status)
            VALUES (?, ?, 'r', ?, 'completed')
            """,
            (f"live-{i:03d}", cid, f"2026-01-{(i % 28) + 1:02d}T12:00:00+00:00"),
        )
    conn.commit()

    payload = list_creator_sessions(
        conn,
        workspace=workspace,
        creator_id=cid,
        limit=50,
        include_cloud=False,
    )
    conn.close()

    assert payload["ok"] is True
    assert payload["total"] == 120
    assert len(payload["sessions"]) == 50
    assert payload["sessions"][0]["kind"] == "live"
    assert payload["sessions"][0]["cloud_available"] is False
