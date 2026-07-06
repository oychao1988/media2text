from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from media2text.core.live.live_observe import LiveObserveService
from media2text.core.live.probe_guard import ProbeExecutionGuard
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway
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
    session_registry=None,
) -> dict[str, Any]:
    """Live probe tick with short DB connections (DL-1).

    Phase 1: poll active recordings (short conn).
    Phase 2: parallel live observe — no tick conn held during Playwright/HTTP.
    Phase 3: stale cleanup + active count (short conn).
    """
    ProbeExecutionGuard.enter_probe_tick()
    try:
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
            dy_poll = douyin.run_poll_active(creator_id=creator_id, deadline=deadline)
            if time.monotonic() >= deadline:
                return {
                    "douyin": dy_poll,
                    "bilibili": {"skipped": "budget_exhausted"},
                    "active_recordings": dy_poll.get("active", 0),
                }
            bi_poll = bilibili.run_poll_active(creator_id=creator_id, deadline=deadline)

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
            dy_fin = douyin.run_finalize()
            bi_fin = bilibili.run_finalize()
            active = dy_fin.get("active", 0)

        return {
            "douyin": {**dy_poll, **dy, **dy_fin},
            "bilibili": {**bi_poll, **bi, **bi_fin},
            "active_recordings": active,
        }
    finally:
        ProbeExecutionGuard.exit_probe_tick(strict=cfg.monitor.probe_guard_strict)
