import pytest

from media2text.api.services.session_playback import (
    find_init_upload,
    find_m3u8_upload,
    find_part_upload,
)
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_find_part_upload_by_part_index(workspace):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="sec", profile_url="https://x", monitor_enabled=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/x",
        session_dir=str(workspace / "live"),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="seg-00005.m4s",
        file_kind="m4s",
        size=100,
        pre_hash="abc",
        part_index=5,
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cf-part-5",
        cloud_relative_path="media2text/douyin/u/live/seg-00005.m4s",
    )
    row = find_part_upload(conn, session_id=sid, part_index=5)
    assert row is not None
    assert row.cloud_file_id == "cf-part-5"
    conn.close()


def test_find_part_upload_by_filename(workspace):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="sec2", profile_url="https://x", monitor_enabled=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/x",
        session_dir=str(workspace / "live2"),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="seg-00002.m4s",
        file_kind="m4s",
        size=100,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cf-part-2",
        cloud_relative_path="media2text/douyin/u/live/seg-00002.m4s",
    )
    row = find_part_upload(conn, session_id=sid, part_index=2)
    assert row is not None
    assert row.cloud_file_id == "cf-part-2"
    conn.close()


def test_find_init_upload(workspace):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="sec_init", profile_url="https://x", monitor_enabled=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/x",
        session_dir=str(workspace / "live_init"),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="init.mp4",
        file_kind="init_mp4",
        size=9,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cf-init",
        cloud_relative_path="media2text/douyin/u/live/init.mp4",
    )
    row = find_init_upload(conn, session_id=sid)
    assert row is not None
    assert row.cloud_file_id == "cf-init"
    conn.close()


def test_find_m3u8_upload(workspace):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="sec_m3u8", profile_url="https://x", monitor_enabled=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/x",
        session_dir=str(workspace / "live_m3u8"),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="master.m3u8",
        file_kind="m3u8",
        size=50,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cf-m3u8",
        cloud_relative_path="media2text/douyin/u/live/master.m3u8",
    )
    row = find_m3u8_upload(conn, session_id=sid)
    assert row is not None
    assert row.cloud_file_id == "cf-m3u8"
    conn.close()
