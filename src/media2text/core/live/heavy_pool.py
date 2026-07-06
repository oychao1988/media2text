"""HeavyPool: finalize (p0 monitor_tasks) + segment_process only (MLS-9 / P3-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from media2text.core.config import AppConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.live.segment_process_pool import SegmentProcessExecutor
from media2text.core.notify import NotifyService

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher


class HeavyPool:
    """Drain finalize and segment_process jobs; post_process stays on PostProcessExecutor."""

    def __init__(
        self,
        *,
        finalize_pool: MonitorExecutor,
        segment_pool: SegmentProcessExecutor,
    ) -> None:
        self._finalize_pool = finalize_pool
        self._segment_pool = segment_pool

    @property
    def finalize_pool(self) -> MonitorExecutor:
        return self._finalize_pool

    @property
    def segment_pool(self) -> SegmentProcessExecutor:
        return self._segment_pool

    def drain(
        self,
        cfg: AppConfig,
        conn,
        *,
        notify: NotifyService,
        watcher: MonitorWatcher | None = None,
    ) -> None:
        min_claim = max(1, cfg.monitor.live_lane_min_claim_per_tick)
        self._finalize_pool.claim_and_submit_priority_zero(
            cfg,
            conn,
            notify=notify,
            watcher=watcher,
            limit=min_claim,
        )
        if cfg.live.segment_pipeline.enabled:
            self._segment_pool.drain_pending(
                cfg,
                conn,
                notify=notify,
                limit=cfg.live.segment_pipeline.max_parallel,
            )

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        self._finalize_pool.shutdown(wait=wait, cancel_futures=cancel_futures)
        self._segment_pool.shutdown(wait=wait, cancel_futures=cancel_futures)
