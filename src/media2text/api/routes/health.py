from __future__ import annotations

from fastapi import APIRouter, Depends

from media2text.api.deps import get_cfg
from media2text.api.services.health import get_health_cache, refresh_health_cache
from media2text.core.config import AppConfig

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return get_health_cache()


@router.post("/doctor/run")
def doctor_run(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return refresh_health_cache(cfg)
