"""has_transcript must reflect loadable sidecars, not DB transcribe_status alone."""

import json

import pytest

from media2text.api.services.sessions_list import (
    _lite_has_transcript,
    list_creator_sessions,
)
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_lite_has_transcript_rejects_completed_without_sidecar(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    assert (
        _lite_has_transcript(
            {"transcribe_status": "completed"},
            ws=ws,
            has_cloud_transcript=False,
        )
        is False
    )


def test_lite_has_transcript_accepts_cloud_flag(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    assert (
        _lite_has_transcript(
            None,
            ws=ws,
            has_cloud_transcript=True,
        )
        is True
    )


def test_list_sessions_marks_cloud_transcript_without_local(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    sec_uid = "MS4wLjABAAAAcloud_tx"
    manifest = {
        "platform": "douyin",
        "sec_uid": sec_uid,
        "live": [],
        "live_groups": [],
    }
    (ws / "creators" / sec_uid).mkdir(parents=True)
    (ws / "creators" / sec_uid / "agent-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    cfg = AppConfig.model_validate({"workspace": str(ws)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url="https://www.douyin.com/user/cloud_tx",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(creator_id=cid, room_id="r", temp_path="")
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        transcribe_status="completed",
        ended=True,
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="20260629T065244Z.transcript.json",
        file_kind="transcript_json",
        size=10,
        pre_hash="x",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-tx",
        cloud_relative_path="media2text/douyin/u/live/x.transcript.json",
    )
    conn.close()

    conn2 = open_db(cfg)
    result = list_creator_sessions(
        conn2,
        workspace=ws,
        creator_id=cid,
        include_cloud=False,
    )
    conn2.close()
    session = next(s for s in result["sessions"] if s["session_id"] == sid)
    assert session["has_transcript"] is True
    assert session["transcript_path"] is None


def test_read_transcript_from_cloud(tmp_path, monkeypatch) -> None:
    from media2text.api.services.transcript import read_transcript_for_session
    from media2text.core.config import AppConfig
    from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
    from media2text.core.workspace import open_db

    ws = tmp_path / "data"
    ws.mkdir()
    (ws / "sessions").mkdir()
    (ws / "sessions" / "aliyundrive.token.json").write_text("{}", encoding="utf-8")

    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "aliyundrive": {"enabled": True},
        }
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAcloud_read",
        profile_url="https://www.douyin.com/user/cloud_read",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(creator_id=cid, room_id="r", temp_path="")
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        transcribe_status="completed",
        ended=True,
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="x.transcript.json",
        file_kind="transcript_json",
        size=10,
        pre_hash="x",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-read",
        cloud_relative_path="media2text/douyin/u/live/x.transcript.json",
    )
    row = LiveSessionRepo(conn).get(sid)
    conn.close()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download_bytes(self, file_id: str) -> bytes:
            assert file_id == "cloud-read"
            return json.dumps({"text": "cloud hello", "segments": []}).encode()

    monkeypatch.setattr(
        "media2text.core.cloud.aliyundrive.AliyunDriveClient.open",
        lambda _path: FakeClient(),
    )

    conn2 = open_db(cfg)
    payload = read_transcript_for_session(row, cfg=cfg, conn=conn2)
    conn2.close()
    assert payload["text"] == "cloud hello"
