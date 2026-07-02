from __future__ import annotations

import sqlite3
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
from media2text.core.storage.db import with_db_lock_retry
from media2text.core.storage.repos import LiveSessionRepo, MonitorTaskRepo
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
        live_pool: MonitorExecutor,
        content_pool: MonitorExecutor,
        post_pool: PostProcessExecutor,
        *,
        segment_pool: SegmentProcessExecutor | None = None,
        stop: threading.Event,
    ) -> None:
        self._cfg = cfg
        self._watcher = watcher
        self._live_pool = live_pool
        self._content_pool = content_pool
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
        self._live_pool.claim_and_submit_priority_zero(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=min_claim,
        )
        self._live_pool.drain_pending(
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
        from media2text.core.live.live_lane import live_lane_priority_count

        live_lane_count = live_lane_priority_count(conn, self._cfg)
        if live_lane_count == 0:
            self._post_pool.drain_pending(
                self._cfg,
                conn,
                notify=self._watcher._notify,
                limit=self._cfg.live.post_process_max_parallel,
            )
        else:
            log.info("post_process_deferred_for_live_lane", count=live_lane_count)
        recording_creator_ids = frozenset(LiveSessionRepo(conn).list_recording_creator_ids())
        if recording_creator_ids:
            released = MonitorTaskRepo(conn).release_running_content_tasks_for_creators(
                sorted(recording_creator_ids)
            )
            if released:
                log.info(
                    "content_tasks_released_for_live",
                    count=released,
                    creator_ids=sorted(recording_creator_ids),
                )
        self._content_pool.drain_pending(
            self._cfg,
            conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=self._cfg.monitor.executor_max_parallel,
            min_priority=10,
            exclude_creator_ids=recording_creator_ids or None,
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
                with_db_lock_retry(lambda: self.tick_once(conn))
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    log.warning("task_scheduler_db_locked", error=str(exc))
                else:
                    raise
            except RuntimeError as exc:
                if self._stop.is_set() and "shutdown" in str(exc).lower():
                    log.debug("task_scheduler_stopped_during_shutdown", error=str(exc))
                    break
                raise
            finally:
                conn.close()
            self._stop.wait(timeout=self._cfg.monitor.scheduler_interval_sec)
