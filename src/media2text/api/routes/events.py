"""Global desktop events WebSocket hub."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services.events_hub import events_hub

router = APIRouter(prefix="/events", tags=["events"])

_PING_INTERVAL_SEC = 30.0


@router.websocket("")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = events_hub.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SEC)
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            except asyncio.TimeoutError:
                ping = event_payload(EventType.PING)
                await websocket.send_text(json.dumps(ping, ensure_ascii=False))
    except WebSocketDisconnect:
        return
    finally:
        events_hub.unsubscribe(queue)
