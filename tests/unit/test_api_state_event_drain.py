import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from media2text.api.schemas.events import EventType
from media2text.core.config import AppConfig
from media2text.core.storage.repos import DesktopEventRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_drain_publishes_creator_updated_to_ws(api_client, workspace, monkeypatch) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    DesktopEventRepo(conn).enqueue_creator_updated("creator-x")
    conn.close()

    monkeypatch.setattr(
        "media2text.api.routes.events._PING_INTERVAL_SEC",
        5.0,
    )
    monkeypatch.setattr(
        "media2text.api.services.state_event_drain._DRAIN_INTERVAL_SEC",
        0.15,
    )

    with api_client.websocket_connect("/api/events") as ws:
        deadline = time.time() + 3.0
        found = False
        while time.time() < deadline:
            try:
                msg = json.loads(ws.receive_text())
            except WebSocketDisconnect:
                break
            if (
                msg.get("type") == EventType.CREATOR_UPDATED.value
                and msg.get("creator_id") == "creator-x"
            ):
                found = True
                break
        assert found

    conn2 = open_db(cfg)
    pending = DesktopEventRepo(conn2).claim_pending(limit=10)
    assert pending == []
    conn2.close()
