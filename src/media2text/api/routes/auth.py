from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from media2text.api.deps import get_cfg, spawn_auth_login
from media2text.core.config import AppConfig
from media2text.core.platform.session_validate import (
    invalidate_session_auth_cache,
    platform_auth_snapshot,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_VALID_PLATFORMS = frozenset({"douyin", "bilibili", "aliyundrive"})


@router.get("/status")
def auth_status(
    cfg: AppConfig = Depends(get_cfg),
    validate: bool = Query(
        True,
        description="Probe platform sessions online (Douyin uses headless browser)",
    ),
    refresh: bool = Query(False, description="Bypass cached validation results"),
) -> dict:
    platforms = {}
    for key in ("douyin", "bilibili", "aliyundrive"):
        platforms[key] = platform_auth_snapshot(
            cfg,
            key,
            validate=validate,
            refresh=refresh,
        ).as_dict()
    return {"ok": True, "platforms": platforms}


@router.post("/login/{platform}")
def auth_login(platform: str, cfg: AppConfig = Depends(get_cfg)) -> dict:
    key = platform.strip().lower()
    if key not in _VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail="platform must be douyin, bilibili, or aliyundrive",
        )
    invalidate_session_auth_cache(workspace=cfg.ensure_workspace(), platform=key)
    return spawn_auth_login(key)
