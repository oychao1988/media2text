from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from media2text.agent.creator_distill.enqueue import enqueue_bootstrap, enqueue_evolve
from media2text.agent.creator_distill.evolve_log import read_evolve_log
from media2text.agent.creator_distill.pool import CreatorAgentJobPool, resolve_distill_workers
from media2text.agent.memory_store import memory_usage_for_profile
from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml
from media2text.core.storage.repos import CreatorAgentJobRepo
from media2text.api.deps import get_cfg
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

router = APIRouter(prefix="/agent/profiles", tags=["agent-profiles"])


class DistillBody(BaseModel):
    force: bool = False


class EvolveBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(alias="sourceId")


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


def _job_dict(job) -> dict[str, Any]:
    if job is None:
        return {}
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "trigger": job.trigger,
        "sourceId": job.source_id,
        "updatedAt": job.updated_at,
    }


@router.post("/creators/{creator_id}/distill")
def trigger_creator_distill(
    creator_id: str,
    body: DistillBody | None = None,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    conn = open_db(cfg)
    try:
        if not CreatorRepo(conn).get(creator_id):
            raise HTTPException(status_code=404, detail="creator not found")
        force = body.force if body else False
        active = CreatorAgentJobRepo(conn).find_active_bootstrap(creator_id)
        if active and active.status == "running" and not force:
            raise HTTPException(status_code=409, detail={"code": "distill_busy"})
        job_id = enqueue_bootstrap(
            cfg,
            conn,
            creator_id=creator_id,
            trigger="manual",
            force=force,
        )
        if job_id is None and active:
            job_id = active.id
    finally:
        conn.close()

    pool = CreatorAgentJobPool(max_workers=resolve_distill_workers(cfg))
    try:
        if job_id:
            wconn = open_db(cfg)
            try:
                job = CreatorAgentJobRepo(wconn).get(job_id)
                if job and job.status == "pending":
                    pool.submit_bootstrap(cfg, job_id=job_id)
            finally:
                wconn.close()
    finally:
        pool.shutdown(wait=False)

    return {"ok": True, "jobId": job_id, "enqueued": bool(job_id)}


@router.get("/creators/{creator_id}/distill-status")
def get_creator_distill_status(creator_id: str, cfg: AppConfig = Depends(get_cfg)) -> dict:
    conn = open_db(cfg)
    try:
        if not CreatorRepo(conn).get(creator_id):
            raise HTTPException(status_code=404, detail="creator not found")
        status = CreatorAgentJobRepo(conn).distill_status(creator_id)
    finally:
        conn.close()

    latest = status.get("latest_bootstrap")
    cache_path = None
    try:
        profile = resolve_profile(creator_id=creator_id, cfg=cfg)
        cache_file = profile.memory_paths.profile_dir / "distill_state.json"
        if cache_file.is_file():
            cache_path = str(cache_file)
    except ValueError:
        pass

    return {
        "ok": True,
        "creatorId": creator_id,
        "byKind": status.get("by_kind") or {},
        "latestBootstrap": _job_dict(latest),
        "distillStatePath": cache_path,
    }


@router.post("/creators/{creator_id}/evolve")
def trigger_creator_evolve(
    creator_id: str,
    body: EvolveBody,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    source_id = body.source_id.strip()
    if not source_id:
        raise HTTPException(status_code=400, detail="source_id required")

    conn = open_db(cfg)
    try:
        if not CreatorRepo(conn).get(creator_id):
            raise HTTPException(status_code=404, detail="creator not found")
        active_bootstrap = CreatorAgentJobRepo(conn).find_active_bootstrap(creator_id)
        if active_bootstrap and active_bootstrap.status == "running":
            raise HTTPException(status_code=409, detail={"code": "distill_busy"})
        job_id = enqueue_evolve(
            cfg,
            conn,
            creator_id=creator_id,
            source_id=source_id,
            trigger="manual",
        )
    finally:
        conn.close()

    pool = CreatorAgentJobPool(max_workers=resolve_distill_workers(cfg))
    try:
        if job_id:
            wconn = open_db(cfg)
            try:
                job = CreatorAgentJobRepo(wconn).get(job_id)
                if job and job.status == "pending":
                    pool.submit_evolve(cfg, job_id=job_id)
            finally:
                wconn.close()
    finally:
        pool.shutdown(wait=False)

    return {
        "ok": True,
        "jobId": job_id,
        "enqueued": bool(job_id),
        "sourceId": source_id,
    }


@router.get("/creators/{creator_id}/evolve-log")
def get_creator_evolve_log(
    creator_id: str,
    offset: int = 0,
    limit: int = 50,
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

    page, total = read_evolve_log(
        profile.memory_paths.profile_dir,
        offset=max(0, offset),
        limit=min(max(1, limit), 200),
    )
    return {
        "ok": True,
        "creatorId": creator_id,
        "offset": offset,
        "limit": limit,
        "total": total,
        "entries": page,
    }
