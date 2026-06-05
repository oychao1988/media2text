from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from media2text.api.deps import get_cfg
from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services import daemon as daemon_svc
from media2text.api.services.events_hub import events_hub
from media2text.core.config import AppConfig

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.get("")
def get_daemon(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return {"ok": True, **daemon_svc.daemon_status(cfg)}


@router.get("/logs")
def get_daemon_logs(
    tail: int = Query(5, ge=1, le=500),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    return daemon_svc.read_daemon_logs(cfg, tail=tail)


@router.post("/start")
def post_daemon_start(cfg: AppConfig = Depends(get_cfg)) -> dict:
    result = daemon_svc.start_daemon(cfg)
    if not result.get("ok"):
        status = 409 if result.get("already_running") else 503
        raise HTTPException(status_code=status, detail=result)
    events_hub.publish(
        event_payload(
            EventType.DAEMON_STARTED,
            extra={"pid": result.get("pid")},
        )
    )
    return result


@router.post("/stop")
def post_daemon_stop(cfg: AppConfig = Depends(get_cfg)) -> dict:
    result = daemon_svc.stop_daemon(cfg)
    if result.get("stopped"):
        events_hub.publish(
            event_payload(
                EventType.DAEMON_STOPPED,
                extra={"pid": result.get("pid")},
            )
        )
    return result
