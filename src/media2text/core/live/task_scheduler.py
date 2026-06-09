from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.notify.drain import drain_once
from media2text.core.notify.outbox import NotifyDaemonGuard
from media2text.core.live.post_process_pool import PostProcessExecutor
from media2text.core.live.segment_process_pool import SegmentProcessExecutor
from media2text.core.live.task_reconciler import reconcile_content, reconcile_live
from media2text.core.storage.repos import LiveSessionRepo
from media2text.core.workspace import open_db

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


class TaskSchedulerLoop:
    """1s tick (R2a): p0 drain → live workers → post_process → content.

    R2c+ (reconciler_enabled): reconcile_live → reconcile_content → then drains (D4).
    """

    def __init__(
        self,
        cfg: AppConfig,
        watcher: MonitorWatcher,
        monitor_pool: MonitorExecutor,
        post_pool: PostProcessExecutor,
        *,
        segment_pool: SegmentProcessExecutor | None = None,
        stop: threading.Event,
    ) -> None:
        self._cfg = cfg
        self._watcher = watcher
        self._monitor_pool = monitor_pool
        self._post_pool = post_pool
        self._segment_pool = segment_pool
        self._stop = stop
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="task-scheduler",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def tick_once(self, conn) -> None:
        if self._cfg.monitor.reconciler_enabled:
            reconcile_live(self._cfg, conn)
            reconcile_content(self._cfg, conn)
        elif self._cfg.monitor.reconciler_log_only:
            n_live = reconcile_live(self._cfg, conn, log_only=True)
            n_content = reconcile_content(self._cfg, conn, log_only=True)
            log.info("reconcile_shadow", live=n_live, content=n_content)

        min_claim = max(1, self._cfg.monitor.live_lane_min_claim_per_tick)
        self._monitor_pool.claim_and_submit_priority_zero(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=min_claim,
        )
        self._monitor_pool.drain_pending(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=self._cfg.monitor.live_worker_max_parallel,
            min_priority=1,
            max_priority=9,
        )
        if self._segment_pool is not None and self._cfg.live.segment_pipeline.enabled:
            self._segment_pool.drain_pending(
                self._cfg,
                conn,
                notify=self._watcher._notify,
                limit=self._cfg.live.segment_pipeline.max_parallel,
            )
        self._post_pool.drain_pending(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            limit=self._cfg.live.post_process_max_parallel,
        )
        content_parallel = self._cfg.monitor.executor_max_parallel
        if LiveSessionRepo(conn).list_active():
            content_parallel = 0
        self._monitor_pool.drain_pending(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=content_parallel,
            min_priority=10,
        )
        try:
            drain_once(self._cfg, limit=20)
        except Exception:
            log.exception("notify_drain_tick_failed")

    def _run(self) -> None:
        NotifyDaemonGuard.enter()
        while not self._stop.is_set():
            conn = open_db(self._cfg)
            try:
                self.tick_once(conn)
            finally:
                conn.close()
            self._stop.wait(timeout=self._cfg.monitor.scheduler_interval_sec)
