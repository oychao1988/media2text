from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from media2text.api.deps import get_cfg, get_db
from media2text.api.schemas.events import EventType, event_payload
from media2text.api.services import creator_avatar as creator_avatar_svc
from media2text.api.services import history_media as history_media_svc
from media2text.api.services import live_snapshot as live_snapshot_svc
from media2text.api.services import recording as recording_svc
from media2text.api.services.events_hub import events_hub
from media2text.api.services import creator_tasks as creator_tasks_svc
from media2text.api.services.sessions_list import list_creator_sessions
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
    item["signature"] = row.signature
    item["follower_count"] = row.follower_count
    item["profile_synced_at"] = row.profile_synced_at
    item["live_snapshot"] = _snapshot_dict(snap)
    item["active_session_id"] = active.id if active else None
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


@router.get("/{creator_id}/avatar")
def get_creator_avatar(
    creator_id: str,
    conn=Depends(get_db),
) -> Response:
    row = CreatorRepo(conn).get(creator_id)
    if not row or not row.avatar_url:
        raise HTTPException(status_code=404, detail="avatar not found")
    try:
        body, content_type = creator_avatar_svc.fetch_creator_avatar(
            row.avatar_url,
            platform=row.platform,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="avatar fetch failed") from exc
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


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
    enqueue_download: bool = Query(False, description="同步成功后加入作品下载队列"),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = creator_svc.sync_creator_catalog(cfg, creator_id)
    if not result.get("ok"):
        code = 401 if result.get("auth_required") else 400
        raise HTTPException(status_code=code, detail=result)
    if enqueue_download:
        dl = creator_tasks_svc.enqueue_creator_download(conn, creator_id=creator_id)
        result["download_queued"] = dl.get("queued", False)
        if dl.get("task_id"):
            result["download_task_id"] = dl["task_id"]
    return result


@router.post("/{creator_id}/download", status_code=202)
def post_enqueue_download(
    creator_id: str,
    conn=Depends(get_db),
) -> dict:
    result = creator_tasks_svc.enqueue_creator_download(conn, creator_id=creator_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    if not result.get("queued"):
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": "already_queued", "creator_id": creator_id},
        )
    return {
        "ok": True,
        "creator_id": creator_id,
        "job_id": result["task_id"],
        "status": "queued",
    }


@router.get("/{creator_id}/sessions")
def list_sessions(
    creator_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    has_transcript: bool | None = Query(None),
    has_summary: bool | None = Query(None),
    status: str | None = Query(None),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = list_creator_sessions(
        conn,
        workspace=cfg.ensure_workspace(),
        creator_id=creator_id,
        limit=limit,
        offset=offset,
        has_transcript=has_transcript,
        has_summary=has_summary,
        status=status,
    )
    return result


@router.post("/{creator_id}/history/{kind}/{item_id}/summarize")
def post_history_summarize(
    creator_id: str,
    kind: str,
    item_id: str,
    force: bool = Query(False),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=400, detail="kind must be live or vod")
    result = history_media_svc.summarize_history_item(
        cfg,
        conn,
        creator_id=creator_id,
        kind=kind,  # type: ignore[arg-type]
        item_id=item_id,
        force=force,
    )
    if not result.get("ok"):
        err = result.get("error")
        code = 404 if err == "not_found" else 400
        if err in ("summarize_disabled", "summarize_unavailable"):
            code = 503
        elif err == "no_transcript":
            code = 400
        raise HTTPException(status_code=code, detail=result)
    return result


@router.post("/{creator_id}/history/vod/{item_id}/retry-download")
def post_history_retry_vod_download(
    creator_id: str,
    item_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    result = history_media_svc.retry_vod_download(
        cfg,
        conn,
        creator_id=creator_id,
        item_id=item_id,
    )
    if not result.get("ok"):
        err = result.get("error")
        code = 404 if err in ("not_found", "creator_not_found") else 409 if err == "invalid_status" else 400
        raise HTTPException(status_code=code, detail=result)
    return result


@router.post("/{creator_id}/history/{kind}/{item_id}/delete-local")
def post_history_delete_local(
    creator_id: str,
    kind: str,
    item_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=400, detail="kind must be live or vod")
    result = history_media_svc.delete_local_media(
        cfg,
        conn,
        creator_id=creator_id,
        kind=kind,  # type: ignore[arg-type]
        item_id=item_id,
    )
    if not result.get("ok"):
        code = 404 if result.get("error") == "not_found" else 400
        if result.get("error") == "session_active":
            code = 409
        raise HTTPException(status_code=code, detail=result)
    return result


@router.post("/{creator_id}/history/{kind}/{item_id}/download-cloud")
def post_history_download_cloud(
    creator_id: str,
    kind: str,
    item_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=400, detail="kind must be live or vod")
    result = history_media_svc.download_from_cloud(
        cfg,
        conn,
        creator_id=creator_id,
        kind=kind,  # type: ignore[arg-type]
        item_id=item_id,
    )
    if not result.get("ok"):
        code = 404 if result.get("error") == "not_found" else 400
        if result.get("error") == "aliyundrive_disabled":
            code = 503
        raise HTTPException(status_code=code, detail=result)
    return result


@router.delete("/{creator_id}/history/{kind}/{item_id}")
def delete_history_item(
    creator_id: str,
    kind: str,
    item_id: str,
    delete_files: bool = Query(True),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=400, detail="kind must be live or vod")
    result = history_media_svc.delete_history_record(
        cfg,
        conn,
        creator_id=creator_id,
        kind=kind,  # type: ignore[arg-type]
        item_id=item_id,
        delete_files=delete_files,
    )
    if not result.get("ok"):
        code = 404 if result.get("error") == "not_found" else 400
        if result.get("error") == "session_active":
            code = 409
        raise HTTPException(status_code=code, detail=result)
    return result


@router.get("/{creator_id}/manifest")
def get_manifest(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    row = CreatorRepo(conn).get(creator_id)
    if not row:
        raise HTTPException(status_code=404, detail="creator not found")
    path = cfg.ensure_workspace() / "creators" / row.sec_uid / "agent-manifest.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="manifest not found")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="manifest read failed") from exc
    return {"ok": True, "creator_id": creator_id, "manifest": manifest}


@router.post("/{creator_id}/recording/start")
def post_recording_start(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = recording_svc.start_recording(cfg, conn, creator_id)
    if not result.get("ok"):
        if result.get("not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result.get("already_recording") or result.get("not_live"):
            raise HTTPException(status_code=409, detail=result)
        if result.get("auth_required"):
            raise HTTPException(status_code=401, detail=result)
        if result.get("platform_changed"):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    events_hub.publish(
        event_payload(
            EventType.RECORDING_STARTED,
            creator_id=creator_id,
            session_id=result.get("session_id"),
        )
    )
    events_hub.publish(
        event_payload(EventType.CREATOR_UPDATED, creator_id=creator_id)
    )
    return result


@router.post("/{creator_id}/recording/stop")
def post_recording_stop(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if not CreatorRepo(conn).get(creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    result = recording_svc.stop_recording(cfg, conn, creator_id)
    if not result.get("ok"):
        if result.get("not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result.get("not_recording"):
            raise HTTPException(status_code=409, detail=result)
        raise HTTPException(status_code=400, detail=result)
    events_hub.publish(
        event_payload(
            EventType.RECORDING_STOPPED,
            creator_id=creator_id,
            session_id=result.get("session_id"),
        )
    )
    events_hub.publish(
        event_payload(EventType.CREATOR_UPDATED, creator_id=creator_id)
    )
    return result


@router.post("/{creator_id}/live/refresh")
def post_live_refresh(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    result = live_snapshot_svc.refresh_creator_live_snapshot(cfg, conn, creator_id)
    if not result.get("ok"):
        if result.get("not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result.get("rate_limited"):
            raise HTTPException(status_code=429, detail=result)
        if result.get("auth_required"):
            raise HTTPException(status_code=401, detail=result)
        if result.get("platform_changed"):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    events_hub.publish(
        event_payload(EventType.CREATOR_UPDATED, creator_id=creator_id)
    )
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


@router.post("/{creator_id}/pipeline/run", status_code=202)
def post_pipeline_run(
    creator_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    from media2text.core.storage.repos import MonitorTaskRepo

    row = CreatorRepo(conn).get(creator_id)
    if not row:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "creator_not_found"})
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=creator_id,
        task_type="pipeline_run",
        dedupe_key=f"pipeline:{creator_id}",
        priority=5,
    )
    if not task_id:
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": "already_queued", "creator_id": creator_id},
        )
    return {"ok": True, "job_id": task_id, "status": "queued", "creator_id": creator_id}
