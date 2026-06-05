import json
import threading
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from media2text.api.schemas.events import EventType
from media2text.api.services.events_hub import events_hub

pytestmark = pytest.mark.desktop


def test_events_ws_receives_runtime_health(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.api.routes.events._PING_INTERVAL_SEC",
        5.0,
    )

    def publish_later() -> None:
        time.sleep(0.2)
        events_hub.publish(
            {
                "type": EventType.RUNTIME_HEALTH.value,
                "health": "healthy",
                "daemon": {"running": True},
            }
        )

    threading.Thread(target=publish_later, daemon=True).start()
    with api_client.websocket_connect("/api/events") as ws:
        deadline = time.time() + 5.0
        found = False
        while time.time() < deadline:
            try:
                msg = json.loads(ws.receive_text())
            except WebSocketDisconnect:
                break
            if msg.get("type") == EventType.RUNTIME_HEALTH.value:
                found = True
                break
        assert found


def test_events_ws_receives_broadcast(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.api.routes.events._PING_INTERVAL_SEC",
        5.0,
    )

    def publish_later() -> None:
        time.sleep(0.2)
        events_hub.publish(
            {
                "type": EventType.DAEMON_STARTED.value,
                "extra": {"pid": 1},
            }
        )

    threading.Thread(target=publish_later, daemon=True).start()
    with api_client.websocket_connect("/api/events") as ws:
        deadline = time.time() + 5.0
        found = False
        while time.time() < deadline:
            try:
                msg = json.loads(ws.receive_text())
            except WebSocketDisconnect:
                break
            if msg.get("type") == EventType.DAEMON_STARTED.value:
                found = True
                break
        assert found


def test_events_ws_ping(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.api.routes.events._PING_INTERVAL_SEC",
        0.2,
    )
    with api_client.websocket_connect("/api/events") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == EventType.PING.value
