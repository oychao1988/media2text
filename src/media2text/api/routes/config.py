from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from media2text.api.config_dto import ConfigPatchDto, apply_dto_patch, config_to_dto
from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig
from media2text.core.errors import ConfigError

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def get_config(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return {"ok": True, "config": config_to_dto(cfg)}


@router.patch("")
def patch_config(
    body: ConfigPatchDto,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    try:
        daemon_restart, agent_reload = apply_dto_patch(cfg, body)
        cfg.save()
    except (ConfigError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    probe = body.llmProviders is not None
    out: dict = {"ok": True, "config": config_to_dto(cfg, probe_providers=probe)}
    if daemon_restart:
        out["requires_daemon_restart"] = daemon_restart
    if agent_reload:
        out["requires_agent_reload"] = agent_reload
    return out
