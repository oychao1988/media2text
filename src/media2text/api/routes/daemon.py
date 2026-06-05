from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig

router = APIRouter(prefix="/daemon", tags=["daemon"])

_GONE = {
    "ok": False,
    "error": "gone",
    "message": "Use /api/runtime instead",
    "use": "/api/runtime",
}


@router.get("")
def get_daemon() -> dict:
    raise HTTPException(status_code=410, detail=_GONE)


@router.get("/logs")
def get_daemon_logs(
    tail: int = Query(5, ge=1, le=500),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    raise HTTPException(status_code=410, detail={**_GONE, "logs": "/api/runtime/logs"})


@router.post("/start")
def post_daemon_start() -> dict:
    raise HTTPException(status_code=410, detail={**_GONE, "start": "/api/runtime/start"})


@router.post("/stop")
def post_daemon_stop() -> dict:
    raise HTTPException(status_code=410, detail={**_GONE, "stop": "/api/runtime/stop"})
