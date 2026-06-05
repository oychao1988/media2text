"""Map creator DB state to desktop status lights."""

from __future__ import annotations

from media2text.core.storage.models import CreatorLiveSnapshotRow, LiveSessionRow

VALID_LIGHTS = frozenset({"green", "yellow", "red", "gray"})

_BADGE_BY_LIGHT: dict[str, dict[str, str]] = {
    "green": {
        "badge": "🟢 录制中",
        "badge_class": "badge-recording",
        "status_abbr": "录",
    },
    "yellow": {
        "badge": "🟡 收尾中",
        "badge_class": "badge-live",
        "status_abbr": "收",
    },
    "red": {
        "badge": "🔴 在播未录",
        "badge_class": "badge-live",
        "status_abbr": "播",
    },
    "gray": {
        "badge": "⚫ 离线",
        "badge_class": "",
        "status_abbr": "离",
    },
}


def _ffmpeg_alive(session: LiveSessionRow) -> bool:
    if session.status != "recording" or not session.ffmpeg_pid or session.ffmpeg_pid <= 0:
        return False
    if (session.reconnect_attempts or 0) > 0:
        return True
    import os

    try:
        os.kill(session.ffmpeg_pid, 0)
        return True
    except OSError:
        return False


def compute_status_light(
    *,
    active_session: LiveSessionRow | None,
    snapshot: CreatorLiveSnapshotRow | None,
) -> dict:
    """Return status_light, is_live, badge fields for API JSON."""
    is_live = bool(snapshot and snapshot.is_live)

    if active_session and _ffmpeg_alive(active_session):
        light = "green"
    elif active_session and active_session.offline_since_at:
        light = "yellow"
    elif active_session and (active_session.transcribe_status or "").lower() == "degraded":
        light = "yellow"
    elif active_session and active_session.status in ("recording", "remuxing"):
        # Active session but ffmpeg not running (startup failure, stale pid, remuxing).
        light = "yellow"
    elif is_live:
        light = "red"
    else:
        light = "gray"

    meta = _BADGE_BY_LIGHT[light]
    return {
        "status_light": light,
        "is_live": is_live,
        **meta,
    }
