from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from media2text.agent.memory_store import memory_usage_for_profile
from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml
from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

router = APIRouter(prefix="/agent/profiles", tags=["agent-profiles"])


class ProfilePatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    display_name: str | None = Field(default=None, alias="displayName")
    enabled_toolsets: list[str] | None = Field(default=None, alias="enabledToolsets")
    disabled_tools: list[str] | None = Field(default=None, alias="disabledTools")
    default_skills: list[str] | None = Field(default=None, alias="defaultSkills")


def _profile_response(cfg: AppConfig, profile) -> dict[str, Any]:
    paths = profile.memory_paths
    return {
        "profileId": profile.profile_id,
        "creatorId": profile.creator_id,
        "paths": {
            "profileDir": str(paths.profile_dir),
            "memory": str(paths.memory),
            "user": str(paths.user),
            "soul": str(paths.soul),
        },
        "profileYaml": profile.profile_yaml,
        "memoryUsage": memory_usage_for_profile(cfg, profile),
        "skillsRoots": [str(p) for p in profile.skills_roots],
        "enabledToolsets": profile.enabled_toolsets,
        "disabledTools": sorted(profile.disabled_tools),
        "defaultSkills": profile.default_skills,
    }


@router.get("/workspace")
def get_workspace_profile(cfg: AppConfig = Depends(get_cfg)) -> dict:
    profile = resolve_profile(creator_id=None, cfg=cfg)
    return {"ok": True, "profile": _profile_response(cfg, profile)}


@router.patch("/workspace")
def patch_workspace_profile(
    body: ProfilePatchBody,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    profile = resolve_profile(creator_id=None, cfg=cfg)
    updates = body.model_dump(by_alias=False, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    save_profile_yaml(profile, updates)
    refreshed = resolve_profile(creator_id=None, cfg=cfg)
    return {"ok": True, "profile": _profile_response(cfg, refreshed)}


@router.get("/creators/{creator_id}")
def get_creator_profile(creator_id: str, cfg: AppConfig = Depends(get_cfg)) -> dict:
    conn = open_db(cfg)
    try:
        if not CreatorRepo(conn).get(creator_id):
            raise HTTPException(status_code=404, detail="creator not found")
    finally:
        conn.close()
    try:
        profile = resolve_profile(creator_id=creator_id, cfg=cfg)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "profile": _profile_response(cfg, profile)}


@router.patch("/creators/{creator_id}")
def patch_creator_profile(
    creator_id: str,
    body: ProfilePatchBody,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    conn = open_db(cfg)
    try:
        if not CreatorRepo(conn).get(creator_id):
            raise HTTPException(status_code=404, detail="creator not found")
    finally:
        conn.close()
    try:
        profile = resolve_profile(creator_id=creator_id, cfg=cfg)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    updates = body.model_dump(by_alias=False, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    save_profile_yaml(profile, updates)
    refreshed = resolve_profile(creator_id=creator_id, cfg=cfg)
    return {"ok": True, "profile": _profile_response(cfg, refreshed)}
