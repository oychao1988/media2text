from __future__ import annotations

from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, Media2TextError
from media2text.core.platform.registry import get_adapter
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

PROFILE_STALE_DAYS_DEFAULT = 7


def is_profile_stale(
    *,
    display_name: str | None,
    profile_synced_at: str | None,
    stale_days: int = PROFILE_STALE_DAYS_DEFAULT,
) -> bool:
    if not display_name or not profile_synced_at:
        return True
    try:
        synced = datetime.fromisoformat(profile_synced_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    age_days = (datetime.now(timezone.utc) - synced).total_seconds() / 86400
    return age_days > stale_days


def platform_session_ready(cfg: AppConfig, platform: str) -> bool:
    """True when the platform has a saved login session under workspace."""
    ws = cfg.ensure_workspace()
    key = platform.strip().lower()
    if key == "douyin":
        from media2text.core.platform.douyin.auth import session_path

        return session_path(ws).is_file()
    if key == "bilibili":
        from media2text.core.platform.bilibili.auth import session_path

        return session_path(ws).is_file()
    return False


def sync_creator_profile(cfg: AppConfig, creator_id: str) -> dict:
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creator = repo.get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}

    try:
        adapter = get_adapter(creator.platform, cfg)
        profile = adapter.get_user_profile(sec_uid=creator.sec_uid)
    except AuthRequired as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "platform": creator.platform,
            "auth_required": True,
            "error": str(exc),
        }
    except Media2TextError as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "platform": creator.platform,
            "auth_required": exc.code == "auth_required",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "creator_id": creator_id,
            "platform": creator.platform,
            "error": str(exc),
        }

    now = datetime.now(timezone.utc).isoformat()
    repo.update_profile(
        creator_id,
        display_name=profile.display_name,
        unique_id=profile.unique_id,
        avatar_url=profile.avatar_url,
        signature=profile.signature,
        follower_count=profile.follower_count,
        profile_synced_at=now,
    )
    return {
        "ok": True,
        "creator_id": creator_id,
        "platform": creator.platform,
        "display_name": profile.display_name,
        "unique_id": profile.unique_id,
        "avatar_url": profile.avatar_url,
        "signature": profile.signature,
        "follower_count": profile.follower_count,
        "profile_synced_at": now,
        "auth_required": False,
    }
