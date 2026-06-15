import json
from unittest.mock import patch

import pytest

from media2text.api.services.history_media import (
    delete_history_record,
    delete_local_media,
    download_from_cloud,
    retry_vod_download,
    summarize_history_item,
)
from media2text.api.services.sessions_list import list_creator_sessions
from media2text.core.config import AppConfig
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_list_sessions_includes_vod_and_cloud_fields(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_mix",
        profile_url="https://www.douyin.com/user/sec_mix",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_mix" / "live"
    video_dir = workspace / "creators" / "sec_mix" / "videos"
    live_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    flv = live_dir / "20260604T100000Z.flv"
    flv.write_bytes(b"flv")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(flv),
    )
    LiveSessionRepo(conn).update_status(
        sid,
        cloud_upload_status="done",
        cloud_file_id="cloud-1",
        cloud_relative_path="media2text/douyin/sec_mix/live/20260604T100000Z.flv",
    )
    vod = video_dir / "7123456789.mp4"
    vod.write_bytes(b"mp4")
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, local_path, updated_at)
        VALUES (?, ?, ?, ?, 'video', 'downloaded', ?, datetime('now'))
        """,
        ("7123456789", cid, "测试作品", 1717500000, str(vod)),
    )
    conn.commit()

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    assert payload["ok"] is True
    kinds = {s["kind"] for s in payload["sessions"]}
    assert kinds == {"live", "vod"}
    live = next(s for s in payload["sessions"] if s["kind"] == "live")
    assert live["cloud_available"] is True
    vod_item = next(s for s in payload["sessions"] if s["kind"] == "vod")
    assert vod_item["title"] == "测试作品"
    assert vod_item["media_available"] is True
    assert vod_item["cloud_available"] is False


def test_delete_local_media_live(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_del_local",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_del_local" / "live" / "x.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"data")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    LiveSessionRepo(conn).update_status(sid, local_path=str(mp4), status="completed")

    result = delete_local_media(cfg, conn, creator_id=cid, kind="live", item_id=sid)
    conn.close()

    assert result["ok"] is True
    assert not mp4.is_file()


def test_delete_history_record_vod(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_del_vod",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_del_vod" / "videos" / "a.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"v")
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, local_path, updated_at)
        VALUES ('aweme1', ?, 't', 1, 'video', 'downloaded', ?, datetime('now'))
        """,
        (cid, str(mp4)),
    )
    conn.commit()

    result = delete_history_record(cfg, conn, creator_id=cid, kind="vod", item_id="aweme1")
    row = AwemeRepo(conn).get("aweme1")
    conn.close()

    assert result["ok"] is True
    assert row is None
    assert not mp4.is_file()


def test_list_sessions_cloud_from_uploads_table(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_cloud_row",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_cloud_row" / "live" / "x.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    LiveSessionRepo(conn).update_status(sid, status="completed", cloud_upload_status="done")
    from media2text.core.storage.repos import CloudUploadRepo

    CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="x.mp4",
        file_kind="mp4",
        local_path=str(mp4),
        size=1,
        pre_hash="abc",
    )
    upload_id = CloudUploadRepo(conn).list_for_session(sid)[0].id
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="fid-table",
        cloud_relative_path="media2text/douyin/sec_cloud_row/live/x.mp4",
    )
    LiveSessionRepo(conn).clear_local_path(sid)

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    live = payload["sessions"][0]
    assert live["cloud_available"] is True
    assert live["cloud_file_id"] == "fid-table"
    assert live["media_available"] is False


def test_list_sessions_vod_cloud_from_uploads_table(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_vod_cloud_row",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_vod_cloud_row" / "videos" / "7123456789.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, local_path, updated_at)
        VALUES (?, ?, ?, ?, 'video', 'downloaded', ?, datetime('now'))
        """,
        ("7123456789", cid, "云备份作品", 1717500000, str(mp4)),
    )
    conn.commit()
    from media2text.core.storage.repos import CloudUploadRepo

    CloudUploadRepo(conn).create(
        session_id="7123456789",
        creator_id=cid,
        platform="douyin",
        file_name="7123456789.mp4",
        file_kind="mp4",
        local_path=str(mp4),
        size=1,
        pre_hash="vodabc",
    )
    upload_id = CloudUploadRepo(conn).list_for_session("7123456789")[0].id
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="fid-vod-table",
        cloud_relative_path="media2text/douyin/sec_vod_cloud_row/videos/7123456789.mp4",
    )
    mp4.unlink()

    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()

    vod_item = next(s for s in payload["sessions"] if s["kind"] == "vod")
    assert vod_item["cloud_available"] is True
    assert vod_item["cloud_file_id"] == "fid-vod-table"
    assert vod_item["media_available"] is False


def test_download_from_cloud_restores_file(workspace) -> None:
    cfg = AppConfig.model_validate(
        {
            "workspace": str(workspace),
            "aliyundrive": {"enabled": True},
        }
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_cloud",
        profile_url="https://example.com",
        platform="douyin",
    )
    target = workspace / "creators" / "sec_cloud" / "live" / "restored.mp4"
    target.parent.mkdir(parents=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(target),
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        cloud_upload_status="done",
        cloud_file_id="fid-1",
        cloud_relative_path="media2text/douyin/sec_cloud/live/restored.mp4",
    )
    LiveSessionRepo(conn).clear_local_path(sid)
    token_path = workspace / "sessions" / "aliyundrive.token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({"access_token": "x"}), encoding="utf-8")

    with patch(
        "media2text.api.services.history_media.AliyunDriveClient.open"
    ) as open_mock:
        client = open_mock.return_value.__enter__.return_value
        client.download_bytes.return_value = b"cloud-bytes"
        result = download_from_cloud(cfg, conn, creator_id=cid, kind="live", item_id=sid)

    conn.close()

    assert result["ok"] is True
    assert target.read_bytes() == b"cloud-bytes"


def test_retry_vod_download_resets_failed_and_enqueues(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_retry",
        profile_url="https://example.com",
        platform="douyin",
    )
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, transcribe_status, updated_at)
        VALUES ('fail1', ?, 't', 1, 'video', 'failed', 'download error', datetime('now'))
        """,
        (cid,),
    )
    conn.commit()

    result = retry_vod_download(cfg, conn, creator_id=cid, item_id="fail1")
    row = AwemeRepo(conn).get("fail1")
    task = conn.execute(
        "SELECT task_type, status FROM monitor_tasks WHERE creator_id = ? ORDER BY id DESC LIMIT 1",
        (cid,),
    ).fetchone()
    conn.close()

    assert result["ok"] is True
    assert result["queued"] is True
    assert row is not None
    assert row.sync_status == "listed"
    assert row.transcribe_status is None
    assert task is not None
    assert task["task_type"] == "download"


def test_retry_vod_download_rejects_non_failed(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_retry2",
        profile_url="https://example.com",
        platform="douyin",
    )
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, updated_at)
        VALUES ('listed1', ?, 't', 1, 'video', 'listed', datetime('now'))
        """,
        (cid,),
    )
    conn.commit()

    result = retry_vod_download(cfg, conn, creator_id=cid, item_id="listed1")
    conn.close()

    assert result["ok"] is False
    assert result["error"] == "invalid_status"


def test_summarize_history_item_disabled(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace), "summarize": {"enabled": False}})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_sum",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_sum" / "live" / "x.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    transcript = mp4.with_suffix(".transcript.json")
    transcript.write_text('{"segments": []}', encoding="utf-8")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    LiveSessionRepo(conn).update_status(sid, local_path=str(mp4), status="completed")

    result = summarize_history_item(
        cfg, conn, creator_id=cid, kind="live", item_id=sid, force=False
    )
    conn.close()

    assert result["ok"] is False
    assert result["error"] == "summarize_disabled"


def test_summarize_history_item_no_transcript(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace), "summarize": {"enabled": True}})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_sum2",
        profile_url="https://example.com",
        platform="douyin",
    )
    missing = workspace / "creators" / "sec_sum2" / "live" / "y.mp4"
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(missing),
    )
    LiveSessionRepo(conn).update_status(sid, local_path=str(missing), status="completed")

    result = summarize_history_item(
        cfg, conn, creator_id=cid, kind="live", item_id=sid, force=False
    )
    conn.close()

    assert result["ok"] is False
    assert result["error"] == "no_transcript"


def test_summarize_history_item_success(workspace, monkeypatch) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace), "summarize": {"enabled": True}})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_sum3",
        profile_url="https://example.com",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_sum3" / "live" / "z.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"x")
    transcript = mp4.with_suffix(".transcript.json")
    transcript.write_text('{"segments": [{"start": 0, "text": "hello"}]}', encoding="utf-8")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        temp_path=str(mp4),
    )
    LiveSessionRepo(conn).update_status(sid, local_path=str(mp4), status="completed")

    monkeypatch.setattr(
        "media2text.api.services.history_media.summarize_engine_available",
        lambda _cfg: (True, None),
    )
    monkeypatch.setattr(
        "media2text.api.services.history_media.create_summarize_backend",
        lambda _cfg: object(),
    )
    monkeypatch.setattr(
        "media2text.api.services.history_media.summarize_one",
        lambda _target, _cfg, _backend, force=False: {
            "summarized": True,
            "summary_path": str(mp4.with_suffix(".summary.md")),
            "skipped": False,
        },
    )
    monkeypatch.setattr(
        "media2text.api.services.history_media.refresh_manifest",
        lambda *args, **kwargs: None,
    )

    result = summarize_history_item(
        cfg, conn, creator_id=cid, kind="live", item_id=sid, force=False
    )
    conn.close()

    assert result["ok"] is True
    assert result["summarized"] is True
    assert result["summary_path"] is not None
