"""Agent turn WebSocket stream (PiEvent-aligned)."""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from media2text.agent import pi_emit
from media2text.api.services.agent_stream_hub import agent_stream_hub

router = APIRouter(prefix="/agent", tags=["agent"])

_PING_INTERVAL_SEC = 30.0


@router.websocket("/stream")
async def agent_stream_ws(
    websocket: WebSocket,
    thread_id: str | None = Query(None, alias="threadId"),
) -> None:
    await websocket.accept()
    await websocket.send_text(json.dumps(pi_emit.sidecar_ready(), ensure_ascii=False))
    q = agent_stream_hub.subscribe(thread_id=thread_id)
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                event = await loop.run_in_executor(
                    None,
                    lambda: q.get(timeout=_PING_INTERVAL_SEC),
                )
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            except queue.Empty:
                ping = {"type": "ping", "payload": {}}
                await websocket.send_text(json.dumps(ping, ensure_ascii=False))
    except WebSocketDisconnect:
        return
    finally:
        agent_stream_hub.unsubscribe(q)
