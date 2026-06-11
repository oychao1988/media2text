"""Session transcript, summary, FLV proxy, and transcript WebSocket."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from media2text.api.deps import get_cfg, get_db
from media2text.api.security import workspace_rel
from media2text.api.services import flv_proxy as flv_proxy_svc
from media2text.api.services.transcript import (
    WS_CLOSE_SESSION_FINALIZED,
    _media_path_for_session,
    is_session_finalized,
    read_summary_text,
    read_transcript_for_session,
    session_sidecar_paths,
    transcript_session_meta,
    transcript_mtime,
)
from media2text.core.config import AppConfig
from media2text.core.manifest import _summary_sidecar_path
from media2text.core.storage.repos import LiveSessionRepo

router = APIRouter(prefix="/sessions", tags=["sessions"])

_TRANSCRIPT_POLL_SEC = 2.0


def _session_payload(
    cfg: AppConfig,
    row,
) -> dict[str, Any]:
    ws = cfg.ensure_workspace()
    sidecars = session_sidecar_paths(row)
    paths = {
        key: workspace_rel(ws, val) for key, val in sidecars.items()
    }
    return {
        "session_id": row.id,
        "creator_id": row.creator_id,
        "room_id": row.room_id,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "status": row.status,
        "local_path": workspace_rel(ws, row.local_path),
        "temp_path": workspace_rel(ws, row.temp_path),
        "pipeline_mode": row.pipeline_mode,
        "transcribe_status": row.transcribe_status,
        "cloud_upload_status": row.cloud_upload_status,
        "cloud_relative_path": row.cloud_relative_path,
        "paths": paths,
    }


@router.get("/{session_id}")
def get_session(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session": _session_payload(cfg, row)}


@router.get("/{session_id}/transcript")
def get_transcript(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    payload = read_transcript_for_session(row)
    return {
        "ok": True,
        "session_id": session_id,
        **transcript_session_meta(row),
        **payload,
    }


@router.get("/{session_id}/summary")
def get_summary(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    media = _media_path_for_session(row)
    if media is None:
        raise HTTPException(status_code=404, detail="no media path for session")
    ws = cfg.ensure_workspace()
    summary_path = workspace_rel(ws, _summary_sidecar_path(str(media)))
    try:
        text = read_summary_text(media)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": True,
                "session_id": session_id,
                "summary_path": summary_path,
                "text": "",
            }
        raise
    return {
        "ok": True,
        "session_id": session_id,
        "summary_path": summary_path,
        "text": text,
    }


@router.get("/{session_id}/stream/proxy")
def stream_proxy(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> StreamingResponse:
    body, headers = flv_proxy_svc.iter_flv_proxy(cfg, conn, session_id)
    return StreamingResponse(body, media_type=headers.get("content-type", "video/x-flv"), headers=headers)


@router.websocket("/{session_id}/transcript/stream")
async def transcript_stream_ws(
    websocket: WebSocket,
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> None:
    await websocket.accept()
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        await websocket.close(code=4404)
        return
    media = _media_path_for_session(row)
    if media is None:
        await websocket.close(code=4404)
        return

    last_mtime: float | None = None
    try:
        while True:
            row = LiveSessionRepo(conn).get(session_id)
            if not row:
                await websocket.close(code=4404)
                return
            media = _media_path_for_session(row)
            if media is None:
                await websocket.close(code=4404)
                return

            mtime = transcript_mtime(row)
            if mtime is not None and mtime != last_mtime:
                last_mtime = mtime
                try:
                    payload = {
                        **read_transcript_for_session(row),
                        **transcript_session_meta(row),
                    }
                except HTTPException:
                    payload = None
                if payload is not None:
                    await websocket.send_text(json.dumps(payload, ensure_ascii=False))

            if is_session_finalized(row):
                if mtime is None or mtime == last_mtime:
                    try:
                        payload = {
                            **read_transcript_for_session(row),
                            **transcript_session_meta(row),
                        }
                        await websocket.send_text(
                            json.dumps(payload, ensure_ascii=False)
                        )
                    except HTTPException:
                        pass
                await websocket.close(code=WS_CLOSE_SESSION_FINALIZED)
                return

            await asyncio.sleep(_TRANSCRIPT_POLL_SEC)
    except WebSocketDisconnect:
        return
