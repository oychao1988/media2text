"""Map creator DB state to desktop status lights."""

from __future__ import annotations

from media2text.core.runtime.status import _age_sec, _stale_snapshot_threshold_sec
from media2text.core.storage.models import CreatorLiveSnapshotRow, LiveSessionRow

VALID_LIGHTS = frozenset({"green", "yellow", "red", "gray"})

def _meta(
    *,
    light: str,
    badge: str,
    status_abbr: str,
    badge_class: str = "",
) -> dict[str, str]:
    return {
        "status_light": light,
        "badge": badge,
        "badge_class": badge_class,
        "status_abbr": status_abbr,
        "status_label": badge.split(" ", 1)[-1],
    }


_BADGE_BY_LIGHT: dict[str, dict[str, str]] = {
    "green": _meta(
        light="green",
        badge="🟢 录制中",
        badge_class="badge-recording",
        status_abbr="录",
    ),
    "yellow": _meta(
        light="yellow",
        badge="🟡 收尾中",
        badge_class="badge-live",
        status_abbr="收",
    ),
    "red": _meta(
        light="red",
        badge="🔴 在播未录",
        badge_class="badge-live",
        status_abbr="播",
    ),
    "gray": _meta(
        light="gray",
        badge="⚫ 离线",
        status_abbr="离",
    ),
}


def _yellow_meta(session: LiveSessionRow) -> dict[str, str]:
    if session.offline_since_at:
        return _BADGE_BY_LIGHT["yellow"]
    transcribe = (session.transcribe_status or "").lower()
    if transcribe == "degraded":
        return _meta(
            light="yellow",
            badge="🟡 转写降级",
            badge_class="badge-live",
            status_abbr="降",
        )
    if session.status == "remuxing":
        return _meta(
            light="yellow",
            badge="🟡 封装中",
            badge_class="badge-live",
            status_abbr="封",
        )
    # Session row is created before ffmpeg pid is assigned (stream resolve window).
    if session.status == "recording" and (
        session.ffmpeg_pid is None or session.ffmpeg_pid <= 0
    ):
        return _meta(
            light="yellow",
            badge="🟡 启动中",
            badge_class="badge-live",
            status_abbr="启",
        )
    return _meta(
        light="yellow",
        badge="🟡 录制异常",
        badge_class="badge-live",
        status_abbr="异",
    )


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


def snapshot_for_status_light(
    cfg,
    snapshot: CreatorLiveSnapshotRow | None,
) -> CreatorLiveSnapshotRow | None:
    """Treat stale is_live snapshots as offline for status lights only."""
    if snapshot is None:
        return None
    age = _age_sec(snapshot.checked_at)
    if age is None or age <= _stale_snapshot_threshold_sec(cfg):
        return snapshot
    if not snapshot.is_live:
        return snapshot
    return CreatorLiveSnapshotRow(
        snapshot.creator_id,
        0,
        snapshot.room_id,
        snapshot.title,
        snapshot.checked_at,
    )


def compute_status_light(
    *,
    active_session: LiveSessionRow | None,
    snapshot: CreatorLiveSnapshotRow | None,
) -> dict:
    """Return status_light, is_live, badge fields for API JSON."""
    is_live = bool(snapshot and snapshot.is_live)

    if active_session and active_session.offline_since_at:
        # Platform offline confirmed; ffmpeg may still drain CDN tail.
        meta = _BADGE_BY_LIGHT["yellow"]
    elif active_session and _ffmpeg_alive(active_session):
        if (active_session.transcribe_status or "").lower() == "degraded":
            meta = _yellow_meta(active_session)
        else:
            meta = _BADGE_BY_LIGHT["green"]
    elif active_session and active_session.status in ("recording", "remuxing"):
        # Active session but ffmpeg not running (startup failure, stale pid, remuxing).
        meta = _yellow_meta(active_session)
    elif is_live:
        meta = _BADGE_BY_LIGHT["red"]
    else:
        meta = _BADGE_BY_LIGHT["gray"]

    return {
        "is_live": is_live,
        **meta,
    }
