from unittest.mock import MagicMock, patch

import httpx
import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _active_session(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_flv",
        profile_url="https://www.douyin.com/user/sec_flv",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="999",
        temp_path=str(workspace / "creators/sec_flv/live/x.flv"),
    )
    conn.close()
    return sid


def test_flv_proxy_streams(api_client, workspace) -> None:
    sid = _active_session(workspace)
    session_file = workspace / "sessions" / "douyin.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"cookies": []}', encoding="utf-8")

    class FakeStream:
        def iter_bytes(self):
            yield b"flv-chunk"

        def close(self):
            pass

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "video/x-flv"}
    fake_response.iter_bytes = FakeStream().iter_bytes
    fake_response.close = FakeStream().close

    fake_client = MagicMock()
    fake_client.build_request.return_value = httpx.Request("GET", "http://upstream/flv")
    fake_client.send.return_value = fake_response
    fake_client.close = MagicMock()

    with (
        patch(
            "media2text.api.services.flv_proxy.resolve_upstream_stream_url",
            return_value="http://upstream/flv",
        ),
        patch(
            "media2text.api.services.flv_proxy.httpx_client_for_platform",
            return_value=fake_client,
        ),
    ):
        r = api_client.get(f"/api/sessions/{sid}/stream/proxy")
    assert r.status_code == 200
    assert r.content == b"flv-chunk"


def test_flv_proxy_not_active(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_done",
        profile_url="https://www.douyin.com/user/sec_done",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(workspace / "x.flv"),
    )
    LiveSessionRepo(conn).update_status(sid, status="completed", ended=True)
    conn.close()
    r = api_client.get(f"/api/sessions/{sid}/stream/proxy")
    assert r.status_code == 409
