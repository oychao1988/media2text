from unittest.mock import MagicMock, patch

import pytest
from starlette.responses import StreamingResponse

from media2text.api.deps import get_cfg, get_db
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _enable_aliyun(api_client, workspace) -> AppConfig:
    cfg = api_client.app.dependency_overrides[get_cfg]()
    cfg.aliyundrive.enabled = True
    token_path = workspace / "sessions" / "aliyundrive.token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"refresh_token":"x"}', encoding="utf-8")
    api = getattr(api_client.app.state, "api_app", None)
    if api is not None:
        api.dependency_overrides[get_cfg] = api_client.app.dependency_overrides[get_cfg]
        api.dependency_overrides[get_db] = api_client.app.dependency_overrides[get_db]
    return cfg


def test_media_cloud_range_when_local_missing(api_client, workspace, monkeypatch) -> None:
    _enable_aliyun(api_client, workspace)
    rel = "creators/sec_vod/videos/7123456789.mp4"
    cfg = AppConfig.load()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_vod",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=rel,
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="7123456789.mp4",
        file_kind="mp4",
        local_path=rel,
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-vod-mp4",
        cloud_relative_path="media2text/douyin/u/videos/7123456789.mp4",
    )
    conn.close()

    mock_resp = StreamingResponse(iter([b"cloud-bytes"]), status_code=206)
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch(
            "media2text.api.services.history_media.AliyunDriveClient.open",
            return_value=mock_client,
        ),
        patch(
            "media2text.api.services.history_media.stream_cloud_file",
            return_value=mock_resp,
        ) as mock_stream,
    ):
        r = api_client.get(
            f"/api/media?path={rel}",
            headers={"Range": "bytes=0-100"},
        )

    assert r.status_code == 206
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs.get("range_header") == "bytes=0-100"


def test_media_cloud_upstream_failure_returns_502(api_client, workspace) -> None:
    _enable_aliyun(api_client, workspace)
    rel = "creators/sec_vod/videos/missing.mp4"
    cfg = AppConfig.load()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_vod",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=rel,
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="missing.mp4",
        file_kind="mp4",
        local_path=rel,
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-bad",
        cloud_relative_path="media2text/douyin/u/videos/missing.mp4",
    )
    conn.close()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch(
            "media2text.api.services.history_media.AliyunDriveClient.open",
            return_value=mock_client,
        ),
        patch(
            "media2text.api.services.history_media.stream_cloud_file",
            side_effect=RuntimeError("cloud upstream status 503"),
        ),
    ):
        r = api_client.get(f"/api/media?path={rel}")

    assert r.status_code == 502
    assert r.json()["detail"] == "cloud media unavailable"


def test_media_still_404_without_cloud_record(api_client, workspace) -> None:
    _enable_aliyun(api_client, workspace)
    r = api_client.get("/api/media?path=creators/x/videos/nope.mp4")
    assert r.status_code == 404
