"""Shared monitor poll interval helpers (MH-1)."""

from __future__ import annotations

from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo

# Distill job drain cadence when using `media2text agent distill drain` (not embedded in monitor).
DISTILL_DRAIN_INTERVAL_SEC = 300.0


def live_poll_interval(cfg: AppConfig) -> int:
    return cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec


def vod_poll_interval_sec(cfg: AppConfig) -> int:
    return cfg.monitor.vod_poll_interval_sec


def bilibili_archive_poll_sec(cfg: AppConfig) -> int:
    return cfg.platforms.bilibili.archive_poll_interval_sec


def bilibili_dynamic_poll_sec(cfg: AppConfig) -> int:
    return cfg.platforms.bilibili.dynamic_poll_interval_sec


def content_poll_fallback_sec(cfg: AppConfig) -> int:
    """Min poll interval when no content-sync creators or all due_at unset."""
    return min(
        vod_poll_interval_sec(cfg),
        bilibili_archive_poll_sec(cfg),
        bilibili_dynamic_poll_sec(cfg),
    )


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_until(due_at: str | None, *, now: datetime) -> float | None:
    """Return seconds until due_at; None if due_at is NULL; 0 if already due."""
    if due_at is None:
        return None
    due = _parse_iso(due_at)
    if due is None:
        return None
    return max(0.0, (due - now).total_seconds())


def compute_slow_tick_sleep_sec(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str | None = None,
    now: datetime | None = None,
) -> float:
    """Seconds until SlowTick should wake for the next content due mark pass."""
    now = now or datetime.now(timezone.utc)
    creators = CreatorRepo(conn)
    targets = creators.list_content_sync_enabled()
    if creator_id:
        row = creators.get(creator_id)
        targets = [row] if row and row.content_sync_enabled else []

    if not targets:
        return float(max(1, content_poll_fallback_sec(cfg)))

    min_future: float | None = None
    for creator in targets:
        if creator.platform == "douyin":
            fields = (creator.vod_due_at,)
        elif creator.platform == "bilibili":
            fields = (creator.archive_due_at, creator.dynamic_due_at)
        else:
            continue
        for due_at in fields:
            sec = _seconds_until(due_at, now=now)
            if sec is None:
                return 1.0
            if sec <= 0:
                return 1.0
            min_future = sec if min_future is None else min(min_future, sec)

    if min_future is None:
        return float(max(1, content_poll_fallback_sec(cfg)))
    return float(max(1.0, min_future))
