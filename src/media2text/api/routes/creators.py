from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from media2text.api.deps import get_cfg, get_db
from media2text.core.config import AppConfig
from media2text.core.creator import service as creator_svc
from media2text.core.creator.service import VALID_AUTO_RECORD_OVERRIDES
from media2text.core.desktop.status_lights import compute_status_light
from media2text.core.platform.profile import sync_creator_profile
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, LiveSnapshotRepo

router = APIRouter(prefix="/creators", tags=["creators"])


class CreatorCreateBody(BaseModel):
    url: str
    platform: str = "douyin"


class CreatorPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    monitor_enabled: bool | None = Field(default=None, alias="monitorEnabled")
    auto_record_override: str | None = Field(default=None, alias="autoRecordOverride")


def _snapshot_dict(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "is_live": bool(row.is_live),
        "room_id": row.room_id,
        "title": row.title,
        "checked_at": row.checked_at,
    }


def _enrich_creator(
    cfg: AppConfig,
    conn,
    row,
) -> dict[str, Any]:
    stale_days = cfg.monitor.profile_stale_days
    item = creator_svc.creator_list_item(row, stale_days=stale_days)
    sessions = LiveSessionRepo(conn)
    snapshots = LiveSnapshotRepo(conn)
    active = sessions.get_active_for_creator(row.id)
    snap = snapshots.get(row.id)
    lights = compute_status_light(active_session=active, snapshot=snap)
    item.update(lights)
    item["avatar_url"] = row.avatar_url
    item["live_snapshot"] = _snapshot_dict(snap)
    return item


@router.get("")
def list_creators(
    all: int = Query(0, alias="all"),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    repo = CreatorRepo(conn)
    rows = repo.list_all() if all else repo.list_monitored()
    creators = [_enrich_creator(cfg, conn, r) for r in rows]
    return {"ok": True, "creators": creators}


@router.get("/{creator_id}")
def get_creator(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    row = CreatorRepo(conn).get(creator_id)
    if not row:
        raise HTTPException(status_code=404, detail="creator not found")
    detail = creator_svc.get_creator_detail(cfg, creator_id)
    assert detail is not None
    sessions = LiveSessionRepo(conn)
    snapshots = LiveSnapshotRepo(conn)
    active = sessions.get_active_for_creator(creator_id)
    snap = snapshots.get(creator_id)
    detail.update(compute_status_light(active_session=active, snapshot=snap))
    detail["live_snapshot"] = _snapshot_dict(snap)
    return {"ok": True, "creator": detail}


@router.post("")
def post_creator(
    body: CreatorCreateBody,
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    result = creator_svc.add_creator_from_url(cfg, url=body.url, platform=body.platform)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.patch("/{creator_id}")
def patch_creator(
    creator_id: str,
    payload: dict[str, Any],
    conn=Depends(get_db),
) -> dict:
    body = CreatorPatchBody.model_validate(payload)
    repo = CreatorRepo(conn)
    if not repo.get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    if body.auto_record_override is not None:
        o = body.auto_record_override.strip().lower()
        if o not in VALID_AUTO_RECORD_OVERRIDES:
            raise HTTPException(
                status_code=400,
                detail="autoRecordOverride must be inherit, on, or off",
            )
        repo.set_auto_record_override(creator_id, o)
    if body.monitor_enabled is not None:
        repo.set_monitor_enabled(creator_id, enabled=body.monitor_enabled)
    row = repo.get(creator_id)
    return {
        "ok": True,
        "creator_id": creator_id,
        "monitor_enabled": bool(row.monitor_enabled) if row else None,
        "auto_record_override": row.auto_record_override if row else None,
    }


@router.delete("/{creator_id}")
def delete_creator(
    creator_id: str,
    delete_media: bool = Query(False),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    result = creator_svc.remove_creator(cfg, creator_id, delete_media=delete_media)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/{creator_id}/sync-profile")
def sync_profile(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = sync_creator_profile(cfg, creator_id)
    if not result.get("ok"):
        code = 401 if result.get("auth_required") else 400
        raise HTTPException(status_code=code, detail=result)
    return result


@router.post("/{creator_id}/sync")
def sync_catalog(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = creator_svc.sync_creator_catalog(cfg, creator_id)
    if not result.get("ok"):
        code = 401 if result.get("auth_required") else 400
        raise HTTPException(status_code=code, detail=result)
    return result


@router.post("/{creator_id}/sync-dynamics")
def sync_dynamics(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    from media2text.core.platform.bilibili.dynamic import sync_creator_dynamics

    row = CreatorRepo(conn).get(creator_id)
    if not row:
        raise HTTPException(status_code=404, detail="creator not found")
    if row.platform != "bilibili":
        raise HTTPException(status_code=400, detail="sync-dynamics only for bilibili")
    result = sync_creator_dynamics(cfg, creator_id)
    if not result.get("ok"):
        code = 401 if result.get("auth_required") else 400
        raise HTTPException(status_code=code, detail=result)
    return result
