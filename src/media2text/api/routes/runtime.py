from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from media2text.api.deps import get_cfg
from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services import runtime as runtime_svc
from media2text.api.services.events_hub import events_hub
from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor

router = APIRouter(prefix="/runtime", tags=["runtime"])


def _supervisor(request: Request) -> MonitorSupervisor:
    sup = getattr(request.app.state, "supervisor", None)
    if sup is None:
        sup = MonitorSupervisor()
        request.app.state.supervisor = sup
    return sup


@router.get("")
def get_runtime(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    return runtime_svc.get_runtime_status(cfg, _supervisor(request))


@router.get("/logs")
def get_runtime_logs(
    tail: int = Query(5, ge=1, le=500),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    return runtime_svc.read_runtime_logs(cfg, tail=tail)


@router.get("/work-queue")
def get_runtime_work_queue(
    limit: int = Query(20, ge=1, le=100),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    return runtime_svc.read_work_queue(cfg, limit=limit)


@router.post("/recover-stale")
def post_runtime_recover_stale(
    older_than_sec: int = Query(120, ge=0, le=86400),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    return runtime_svc.recover_runtime_stale_work(cfg, older_than_sec=older_than_sec)


@router.post("/start")
def post_runtime_start(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    result = runtime_svc.start_runtime(cfg, _supervisor(request))
    if not result.get("ok"):
        status = 409 if result.get("already_running") or result.get("already_running_external") else 503
        raise HTTPException(status_code=status, detail=result)
    events_hub.publish(
        event_payload(
            EventType.DAEMON_STARTED,
            extra={"managed_by": "embedded"},
        )
    )
    return result


@router.post("/stop")
def post_runtime_stop(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    sup = _supervisor(request)
    managed_by = sup.status(cfg).managed_by
    result = runtime_svc.stop_runtime(cfg, sup)
    if result.get("not_owner"):
        raise HTTPException(status_code=403, detail=result)
    if not result.get("ok") and result.get("error") == "stop_timeout":
        raise HTTPException(status_code=409, detail=result)
    if result.get("stopped"):
        events_hub.publish(
            event_payload(
                EventType.DAEMON_STOPPED,
                extra={"managed_by": managed_by if managed_by != "none" else "embedded"},
            )
        )
    return result


@router.post("/takeover")
def post_runtime_takeover(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    result = runtime_svc.takeover_runtime(cfg, _supervisor(request))
    start = result.get("start") or {}
    if not result.get("ok"):
        if result.get("error") == "stop_timeout":
            raise HTTPException(status_code=409, detail=result)
        status = 409 if start.get("already_running") else 503
        raise HTTPException(status_code=status, detail=result)
    events_hub.publish(
        event_payload(
            EventType.DAEMON_STARTED,
            extra={"managed_by": "embedded", "takeover": True},
        )
    )
    return result


@router.post("/restart")
def post_runtime_restart(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    result = runtime_svc.restart_runtime(cfg, _supervisor(request))
    if result.get("not_owner"):
        raise HTTPException(status_code=403, detail=result)
    stop = result.get("stop") or {}
    if not stop.get("ok") and stop.get("error") == "stop_timeout":
        raise HTTPException(status_code=409, detail=stop)
    start = result.get("start") or {}
    if not result.get("ok"):
        status = 409 if start.get("already_running_external") else 503
        raise HTTPException(status_code=status, detail=result)
    managed_by = result.get("managed_by", "embedded")
    events_hub.publish(
        event_payload(
            EventType.DAEMON_STARTED,
            extra={"managed_by": managed_by, "restart": True},
        )
    )
    return result


@router.post("/handoff")
def post_runtime_handoff(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    """Stop embedded supervisor and spawn CLI ``monitor watch --daemon``."""
    result = runtime_svc.handoff_runtime(cfg, _supervisor(request))
    start = result.get("start") or {}
    if not result.get("ok"):
        status = 409 if start.get("already_running_external") else 503
        raise HTTPException(status_code=status, detail=result)
    events_hub.publish(
        event_payload(
            EventType.DAEMON_STARTED,
            extra={"managed_by": "external", "handoff": True},
        )
    )
    return result
