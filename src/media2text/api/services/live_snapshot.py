"""On-demand live snapshot refresh for desktop API."""

from __future__ import annotations

import time
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, PlatformChanged
from media2text.core.live.snapshot import upsert_live_snapshot
from media2text.core.platform.registry import get_adapter
from media2text.core.storage.repos import CreatorRepo

_REFRESH_COOLDOWN_SEC = 30.0
_last_refresh: dict[str, float] = {}


def refresh_creator_live_snapshot(
    cfg: AppConfig,
    conn,
    creator_id: str,
) -> dict[str, Any]:
    row = CreatorRepo(conn).get(creator_id)
    if not row:
        return {"ok": False, "error": "creator not found", "not_found": True}

    now = time.monotonic()
    last = _last_refresh.get(creator_id)
    if last is not None and (now - last) < _REFRESH_COOLDOWN_SEC:
        retry_after = int(_REFRESH_COOLDOWN_SEC - (now - last)) + 1
        return {
            "ok": False,
            "rate_limited": True,
            "retry_after_sec": retry_after,
            "error": f"refresh rate limit ({_REFRESH_COOLDOWN_SEC:.0f}s per creator)",
        }

    adapter = get_adapter(row.platform, cfg)
    try:
        live_info = adapter.get_live_room(sec_uid=row.sec_uid)
    except AuthRequired as exc:
        return {"ok": False, "auth_required": True, "error": str(exc)}
    except PlatformChanged as exc:
        return {"ok": False, "platform_changed": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    upsert_live_snapshot(conn, creator_id, live_info)
    _last_refresh[creator_id] = now
    snap = {
        "is_live": bool(live_info.is_live),
        "room_id": live_info.room_id,
        "title": live_info.title,
    }
    return {"ok": True, "creator_id": creator_id, "live_snapshot": snap}


def clear_refresh_rate_limit_for_tests() -> None:
    """Reset in-memory rate limit state (unit tests only)."""
    _last_refresh.clear()
