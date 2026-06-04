import json
import pytest
from starlette.websockets import WebSocketDisconnect

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_partial(workspace) -> tuple[str, str]:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_ws",
        profile_url="https://www.douyin.com/user/sec_ws",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_ws" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T120000Z.flv"
    flv.write_bytes(b"\x00")
    partial = flv.with_suffix(".transcript.partial.json")
    partial.write_text(
        json.dumps(
            {
                "text": "ws-line",
                "segments": [{"start": 0, "end": 1, "text": "ws-line"}],
            }
        ),
        encoding="utf-8",
    )
    sessions = LiveSessionRepo(conn)
    sid = sessions.create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(flv),
    )
    sessions.update_status(sid, status="completed", ended=True)
    conn.close()
    return sid, str(partial)


def test_transcript_ws_pushes_partial(api_client, workspace) -> None:
    sid, _ = _seed_partial(workspace)
    with api_client.websocket_connect(
        f"/api/sessions/{sid}/transcript/stream"
    ) as ws:
        msg = json.loads(ws.receive_text())
        assert msg["text"] == "ws-line"
        assert msg["partial"] is True


def test_transcript_ws_unknown_session(api_client) -> None:
    with api_client.websocket_connect(
        "/api/sessions/00000000-0000-0000-0000-000000000099/transcript/stream"
    ) as ws:
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()
