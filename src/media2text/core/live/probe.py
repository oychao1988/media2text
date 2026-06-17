from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from media2text.core.live.probe_guard import ProbeExecutionGuard

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


def run_live_probe_tick(
    cfg: AppConfig,
    conn,
    *,
    douyin: DouyinLiveWatcher,
    bilibili: BilibiliLiveWatcher,
    creator_id: str | None = None,
) -> dict[str, Any]:
    from media2text.core.storage.repos import CreatorRepo

    n_targets = 1
    if creator_id:
        n_targets = 1
    else:
        n_targets = sum(
            1 for c in CreatorRepo(conn).list_monitored() if c.platform in ("douyin", "bilibili")
        )
    ProbeExecutionGuard.enter_probe_tick()
    try:
        deadline = time.monotonic() + probe_budget_sec(cfg, n_targets)
        dy = douyin.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
        if time.monotonic() >= deadline:
            return {"douyin": dy, "bilibili": {"skipped": "budget_exhausted"}}
        bi = bilibili.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
        return {"douyin": dy, "bilibili": bi}
    finally:
        ProbeExecutionGuard.exit_probe_tick(strict=cfg.monitor.probe_guard_strict)
