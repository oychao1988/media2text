from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from media2text.core.config import AppConfig
    from media2text.core.platform.bilibili.live import LiveWatcher as BilibiliLiveWatcher
    from media2text.core.platform.douyin.live import LiveWatcher as DouyinLiveWatcher


def probe_budget_sec(cfg: AppConfig) -> float:
    if cfg.monitor.probe_tick_budget_sec > 0:
        return float(cfg.monitor.probe_tick_budget_sec)
    live_poll = cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec
    return 2.0 * live_poll


def run_live_probe_tick(
    cfg: AppConfig,
    conn,
    *,
    douyin: DouyinLiveWatcher,
    bilibili: BilibiliLiveWatcher,
    creator_id: str | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + probe_budget_sec(cfg)
    dy = douyin.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    if time.monotonic() >= deadline:
        return {"douyin": dy, "bilibili": {"skipped": "budget_exhausted"}}
    bi = bilibili.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    return {"douyin": dy, "bilibili": bi}
