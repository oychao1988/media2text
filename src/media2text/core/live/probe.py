from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from media2text.core.live.live_observe import LiveObserveService
from media2text.core.live.probe_guard import ProbeExecutionGuard
from media2text.core.storage.db import with_db_lock_retry
from media2text.core.storage.write_gateway import ensure_write_gateway_started, gateway_write, get_write_gateway
from media2text.core.workspace import open_db

if TYPE_CHECKING:
    from media2text.core.config import AppConfig
    from media2text.core.platform.bilibili.live import LiveWatcher as BilibiliLiveWatcher
    from media2text.core.platform.douyin.live import LiveWatcher as DouyinLiveWatcher


# Playwright live probes share a process-wide semaphore (see playwright_env).
_PLAYWRIGHT_PROBE_SLOTS = 2
# Typical headless profile visit + XHR capture (seconds).
_PROBE_SEC_PER_CREATOR = 28.0


def probe_workers(cfg: AppConfig, n_targets: int) -> int:
    n = cfg.monitor.probe_parallelism or cfg.live.scan_concurrency
    return min(max(1, n), n_targets, _PLAYWRIGHT_PROBE_SLOTS)


def probe_budget_sec(cfg: AppConfig, n_targets: int = 1) -> float:
    if cfg.monitor.probe_tick_budget_sec > 0:
        return float(cfg.monitor.probe_tick_budget_sec)
    live_poll = cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec
    workers = probe_workers(cfg, max(1, n_targets))
    batches = math.ceil(max(1, n_targets) / workers)
    return max(2.0 * live_poll, batches * _PROBE_SEC_PER_CREATOR + 5.0)


def _count_live_probe_targets(cfg: AppConfig, conn, *, creator_id: str | None) -> int:
    from media2text.core.storage.repos import CreatorRepo

    if creator_id:
        return 1
    return sum(
        1
        for c in CreatorRepo(conn).list_monitored()
        if c.platform in ("douyin", "bilibili")
    )


def run_live_probe_tick(
    cfg: AppConfig,
    *,
    douyin: DouyinLiveWatcher,
    bilibili: BilibiliLiveWatcher,
    creator_id: str | None = None,
    conn=None,
    session_registry=None,
) -> dict[str, Any]:
    """Live probe tick with short DB connections (DL-1).

    Phase 1: poll active recordings (short conn).
    Phase 2: parallel live observe — no tick conn held during Playwright/HTTP.
    Phase 3: stale cleanup + active count (short conn).

    ``conn`` is deprecated; kept for unit tests that pass a shared connection.
    """
    ProbeExecutionGuard.enter_probe_tick()
    try:
        if conn is not None:
            return _run_live_probe_tick_legacy(
                cfg,
                conn,
                douyin=douyin,
                bilibili=bilibili,
                creator_id=creator_id,
            )

        conn = open_db(cfg)
        try:
            n_targets = _count_live_probe_targets(cfg, conn, creator_id=creator_id)
        finally:
            conn.close()

        deadline = time.monotonic() + probe_budget_sec(cfg, n_targets)
        ensure_write_gateway_started(cfg)
        gateway = get_write_gateway(cfg)

        if session_registry is not None:
            poll = LiveObserveService.poll_active_recordings(
                cfg,
                registry=session_registry,
                gateway=gateway,
            )
            dy_poll = poll
            bi_poll = poll
        else:
            conn = open_db(cfg)
            try:
                dy_poll = douyin.run_poll_active(
                    conn=conn, creator_id=creator_id, deadline=deadline
                )
                if time.monotonic() >= deadline:
                    return {
                        "douyin": dy_poll,
                        "bilibili": {"skipped": "budget_exhausted"},
                        "active_recordings": dy_poll.get("active", 0),
                    }
                bi_poll = bilibili.run_poll_active(
                    conn=conn, creator_id=creator_id, deadline=deadline
                )
            finally:
                conn.close()

        dy = douyin.run_probe_observe(creator_id=creator_id, deadline=deadline)
        if time.monotonic() >= deadline:
            return {
                "douyin": {**dy_poll, **dy},
                "bilibili": {"skipped": "budget_exhausted"},
                "active_recordings": dy_poll.get("active", 0),
            }
        bi = bilibili.run_probe_observe(creator_id=creator_id, deadline=deadline)

        if session_registry is not None:
            fin = LiveObserveService.run_finalize(cfg, gateway=gateway)
            dy_fin = fin
            bi_fin = fin
            active = fin.get("active", 0)
        else:
            conn = open_db(cfg)
            try:
                dy_fin: dict[str, Any] = {}
                bi_fin: dict[str, Any] = {}
                active = 0

                def _finalize(wconn) -> None:
                    nonlocal dy_fin, bi_fin, active
                    dy_fin = douyin.run_finalize(conn=wconn)
                    bi_fin = bilibili.run_finalize(conn=wconn)
                    from media2text.core.storage.repos import LiveSessionRepo

                    active = len(LiveSessionRepo(wconn, cfg=cfg).list_active())

                gateway_write(cfg, _finalize, label="probe.finalize")
            finally:
                conn.close()

        return {
            "douyin": {**dy_poll, **dy, **dy_fin},
            "bilibili": {**bi_poll, **bi, **bi_fin},
            "active_recordings": active,
        }
    finally:
        ProbeExecutionGuard.exit_probe_tick(strict=cfg.monitor.probe_guard_strict)


def _run_live_probe_tick_legacy(
    cfg: AppConfig,
    conn,
    *,
    douyin: DouyinLiveWatcher,
    bilibili: BilibiliLiveWatcher,
    creator_id: str | None = None,
) -> dict[str, Any]:
    n_targets = _count_live_probe_targets(cfg, conn, creator_id=creator_id)
    deadline = time.monotonic() + probe_budget_sec(cfg, n_targets)
    dy = douyin.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    if time.monotonic() >= deadline:
        return {"douyin": dy, "bilibili": {"skipped": "budget_exhausted"}}
    bi = bilibili.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    from media2text.core.storage.repos import LiveSessionRepo

    return {
        "douyin": dy,
        "bilibili": bi,
        "active_recordings": len(LiveSessionRepo(conn).list_active()),
    }


def run_poll_active_tick(
    cfg: AppConfig,
    conn,
    *,
    douyin: DouyinLiveWatcher,
    bilibili: BilibiliLiveWatcher,
    creator_id: str | None = None,
    deadline: float | None = None,
) -> None:
    """Poll active recordings for both platforms under write lock."""

    def _poll() -> None:
        douyin.run_poll_active(conn=conn, creator_id=creator_id, deadline=deadline)
        bilibili.run_poll_active(conn=conn, creator_id=creator_id, deadline=deadline)

    with_db_lock_retry(_poll)
