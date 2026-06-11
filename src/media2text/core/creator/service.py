"""Creator registry operations shared by CLI and desktop API."""

from __future__ import annotations

import shutil
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.errors import ParseFailed
from media2text.core.manifest import refresh_manifest
from media2text.core.platform.bilibili.resolver import resolve_mid
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.platform.douyin.resolver import resolve_sec_uid
from media2text.core.platform.profile import (
    is_profile_stale,
    platform_session_ready,
    sync_creator_profile,
)
from media2text.core.platform.vod import sync_creator
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

VALID_AUTO_RECORD_OVERRIDES = frozenset({"inherit", "on", "off"})


def creator_list_item(row, *, stale_days: int) -> dict[str, Any]:
    return {
        "id": row.id,
        "platform": row.platform,
        "sec_uid": row.sec_uid,
        "display_name": row.display_name,
        "unique_id": row.unique_id,
        "profile_url": row.profile_url,
        "monitor_enabled": bool(row.monitor_enabled),
        "content_sync_enabled": bool(row.content_sync_enabled),
        "profile_stale": is_profile_stale(
            display_name=row.display_name,
            profile_synced_at=row.profile_synced_at,
            stale_days=stale_days,
        ),
        "auto_record_override": row.auto_record_override or "inherit",
    }


def add_creator_from_url(
    cfg: AppConfig,
    *,
    url: str,
    platform: str = "douyin",
) -> dict[str, Any]:
    plat = platform.strip().lower()
    if plat not in ("douyin", "bilibili"):
        return {
            "ok": False,
            "error": "platform must be douyin or bilibili",
            "platform": plat,
        }

    ws = cfg.ensure_workspace()
    client = None
    session = session_path(ws)
    if plat == "douyin" and session.is_file():
        client = client_from_storage(session)

    try:
        if plat == "bilibili":
            sec_uid = resolve_mid(url)
        else:
            sec_uid = resolve_sec_uid(url, client)
    except ParseFailed as exc:
        return {"ok": False, "platform": plat, "error": str(exc)}

    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    existing = repo.get_by_sec_uid(sec_uid, platform=plat)
    if existing:
        return {
            "ok": True,
            "platform": plat,
            "creator_id": existing.id,
            "sec_uid": sec_uid,
            "already_exists": True,
            "monitor_enabled": bool(existing.monitor_enabled),
        }

    creator_id = repo.add(
        sec_uid=sec_uid,
        profile_url=url,
        platform=plat,
        monitor_enabled=False,
    )
    profile_result: dict | None = None
    if platform_session_ready(cfg, plat):
        profile_result = sync_creator_profile(cfg, creator_id)

    row = repo.get(creator_id)
    return {
        "ok": True,
        "platform": plat,
        "creator_id": creator_id,
        "sec_uid": sec_uid,
        "monitor_enabled": False,
        "display_name": row.display_name if row else None,
        "unique_id": row.unique_id if row else None,
        "profile_synced": bool(profile_result and profile_result.get("ok")),
        "profile_error": (
            profile_result.get("error")
            if profile_result and not profile_result.get("ok")
            else None
        ),
        "auth_required": bool(profile_result and profile_result.get("auth_required")),
    }


def remove_creator(
    cfg: AppConfig,
    creator_id: str,
    *,
    delete_media: bool = False,
) -> dict[str, Any]:
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creator = repo.get(creator_id)
    if not creator:
        return {
            "ok": False,
            "error": "creator not found",
            "creator_id": creator_id,
        }
    sec_uid = creator.sec_uid
    ok = repo.remove(creator_id)
    deleted_media = False
    if ok and delete_media and sec_uid:
        media_dir = cfg.ensure_workspace() / "creators" / sec_uid
        if media_dir.is_dir():
            shutil.rmtree(media_dir)
            deleted_media = True
    return {
        "ok": ok,
        "creator_id": creator_id,
        "delete_media": delete_media,
        "deleted_media": deleted_media,
    }


def get_creator_detail(cfg: AppConfig, creator_id: str) -> dict[str, Any] | None:
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    row = creators.get(creator_id)
    if not row:
        return None
    stale_days = cfg.monitor.profile_stale_days
    payload = creator_list_item(row, stale_days=stale_days)
    payload.update(
        {
            "avatar_url": row.avatar_url,
            "signature": row.signature,
            "follower_count": row.follower_count,
            "profile_synced_at": row.profile_synced_at,
            "aweme_count": creators.count_awemes(creator_id),
            "pending_download_count": creators.count_pending_download(creator_id),
        }
    )
    sessions = LiveSessionRepo(conn)
    latest = sessions.get_latest_for_creator(creator_id)
    if latest:
        payload["latest_live_session"] = {
            "session_id": latest.id,
            "started_at": latest.started_at,
            "status": latest.status,
            "pipeline_mode": latest.pipeline_mode,
            "transcribe_status": latest.transcribe_status,
        }
    else:
        payload["latest_live_session"] = None
    return payload


def sync_creator_catalog(cfg: AppConfig, creator_id: str) -> dict[str, Any]:
    result = sync_creator(cfg, creator_id)
    if result.get("ok"):
        conn = open_db(cfg)
        creator = CreatorRepo(conn).get(creator_id)
        if creator:
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace())
    return result
