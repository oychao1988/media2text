from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_creator(workspace, *, sec_uid: str = "sec_live") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        monitor_enabled=True,
    )
    conn.close()
    return cid


def test_recording_start_success(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    mock_core = MagicMock()
    mock_core.start_recording_for_creator.return_value = {
        "session_id": "sess-1",
        "temp_path": "/tmp/x.flv",
        "pid": 12345,
    }
    with patch(
        "media2text.api.services.recording._build_core",
        return_value=mock_core,
    ):
        r = api_client.post(f"/api/creators/{cid}/recording/start")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["session_id"] == "sess-1"
    mock_core.start_recording_for_creator.assert_called_once_with(cid)


def test_recording_start_not_live_409(api_client, workspace) -> None:
    from media2text.core.errors import NotLive

    cid = _seed_creator(workspace)
    mock_core = MagicMock()
    mock_core.start_recording_for_creator.side_effect = NotLive("offline")
    with patch(
        "media2text.api.services.recording._build_core",
        return_value=mock_core,
    ):
        r = api_client.post(f"/api/creators/{cid}/recording/start")
    assert r.status_code == 409
    assert r.json()["detail"]["not_live"] is True


def test_recording_start_already_recording_409(api_client, workspace) -> None:
    from media2text.core.errors import AlreadyRecording

    cid = _seed_creator(workspace)
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/tmp/active.flv",
        ffmpeg_pid=999,
    )
    conn.close()

    mock_core = MagicMock()
    mock_core.start_recording_for_creator.side_effect = AlreadyRecording("busy")
    with patch(
        "media2text.api.services.recording._build_core",
        return_value=mock_core,
    ):
        r = api_client.post(f"/api/creators/{cid}/recording/start")
    assert r.status_code == 409
    assert r.json()["detail"]["already_recording"] is True


def test_recording_stop_success(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    mock_core = MagicMock()
    mock_core.stop_recording_for_creator.return_value = {
        "session_id": "sess-1",
        "status": "completed",
    }
    with patch(
        "media2text.api.services.recording._build_core",
        return_value=mock_core,
    ):
        r = api_client.post(f"/api/creators/{cid}/recording/stop")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    mock_core.stop_recording_for_creator.assert_called_once_with(cid)


def test_recording_stop_not_recording_409(api_client, workspace) -> None:
    from media2text.core.errors import NotRecording

    cid = _seed_creator(workspace)
    mock_core = MagicMock()
    mock_core.stop_recording_for_creator.side_effect = NotRecording("none")
    with patch(
        "media2text.api.services.recording._build_core",
        return_value=mock_core,
    ):
        r = api_client.post(f"/api/creators/{cid}/recording/stop")
    assert r.status_code == 409
    assert r.json()["detail"]["not_recording"] is True
