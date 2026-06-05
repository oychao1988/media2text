from __future__ import annotations

from fastapi import APIRouter, Depends

from media2text.api.deps import get_cfg, get_db
from media2text.api.services.health import get_health_cache, refresh_health_cache
from media2text.core.config import AppConfig
from media2text.core.doctor_repair import repair_environment

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return get_health_cache()


@router.post("/doctor/run")
def doctor_run(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return refresh_health_cache(cfg)


@router.post("/doctor/repair")
def doctor_repair(cfg: AppConfig = Depends(get_cfg), conn=Depends(get_db)) -> dict:
    result = repair_environment(cfg, conn)
    cache = refresh_health_cache(cfg)
    return {
        "ok": True,
        "repair_ok": result["repair_ok"],
        "actions": result["actions"],
        "checks": cache["checks"],
        "doctor_ok": cache["doctor_ok"],
        "compliance_accepted": cache["compliance_accepted"],
        "index_stale": cache["index_stale"],
        "monitor_lock_pid": cache["monitor_lock_pid"],
    }
