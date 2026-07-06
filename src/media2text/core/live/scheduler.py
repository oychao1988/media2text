from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from media2text.core.runtime.heartbeat import write_heartbeat

from media2text.core.config import AppConfig
from media2text.core.live.heavy_pool import HeavyPool
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.notify.outbox import NotifyDaemonGuard
from media2text.core.live.post_process_pool import PostProcessExecutor, resolve_post_process_workers
from media2text.core.live.segment_process_pool import (
    SegmentProcessExecutor,
    resolve_segment_process_workers,
)
from media2text.core.live.segment_watcher import SegmentWatcher, set_segment_watcher
from media2text.core.live.probe import run_live_probe_tick
from media2text.core.live.loop import run_live_inline_decisions
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.errors import ReconcilerDisabledError
from media2text.core.monitor.intervals import (
    bilibili_archive_poll_sec,
    bilibili_dynamic_poll_sec,
    compute_slow_tick_sleep_sec,
    live_poll_interval,
    vod_poll_interval_sec,
)
from media2text.core.workspace import open_db
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


class LiveTickLoop:
    """Dedicated thread: live probe only (LP-01/02/03); no inline finalize drain."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        *,
        creator_id: str | None,
        stop: threading.Event,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._creator_id = creator_id
        self._stop = stop
        self._on_tick = on_tick
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="live-probe",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        NotifyDaemonGuard.enter()
        live_poll = live_poll_interval(self._cfg)
        while not self._stop.is_set():
            if self._on_tick is not None:
                self._on_tick()
            else:
                write_heartbeat(
                    self._cfg.ensure_workspace(),
                    last_tick_at=datetime.now(timezone.utc).isoformat(),
                )
            result = run_live_probe_tick(
                self._cfg,
                douyin=self._watcher._douyin_live,
                bilibili=self._watcher._bilibili_live,
                creator_id=self._creator_id,
                session_registry=self._watcher.session_registry,
            )
            if self._cfg.live.inline_decisions:
                run_live_inline_decisions(self._cfg, self._watcher)
            active = int(result.get("active_recordings") or 0)
            log.info("live_tick", active_recordings=active, live_poll_sec=live_poll)
            if self._on_tick is not None:
                self._on_tick()
            else:
                write_heartbeat(
                    self._cfg.ensure_workspace(),
                    last_tick_at=datetime.now(timezone.utc).isoformat(),
                )
            self._stop.wait(timeout=live_poll)


class SlowTickLoop:
    """Dedicated thread: VOD, archive, and dynamic ticks on their intervals."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        *,
        creator_id: str | None,
        stop: threading.Event,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._creator_id = creator_id
        self._stop = stop
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="slow-tick",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        NotifyDaemonGuard.enter()
        while not self._stop.is_set():
            conn = open_db(self._cfg)
            try:
                self._watcher._run_vod_tick(conn=conn, creator_id=self._creator_id)
                self._watcher._run_archive_tick(conn=conn, creator_id=self._creator_id)
                self._watcher._run_dynamic_tick(conn=conn, creator_id=self._creator_id)
            finally:
                conn.close()
            sleep_conn = open_db(self._cfg)
            try:
                sleep_sec = compute_slow_tick_sleep_sec(
                    self._cfg,
                    sleep_conn,
                    creator_id=self._creator_id,
                )
            finally:
                sleep_conn.close()
            self._stop.wait(timeout=sleep_sec)


class MonitorScheduler:
    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        *,
        on_live_tick: Callable[[], None] | None = None,
        stop: threading.Event | None = None,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._on_live_tick = on_live_tick
        self._stop = stop if stop is not None else threading.Event()
        max_workers = resolve_post_process_workers(cfg)
        self._post_pool = PostProcessExecutor(max_workers=max_workers)
        seg_workers = resolve_segment_process_workers(cfg)
        self._segment_pool = SegmentProcessExecutor(max_workers=seg_workers)
        self._heavy_pool = HeavyPool(
            finalize_pool=MonitorExecutor(
                max_workers=max(cfg.monitor.live_worker_max_parallel, 1),
            ),
            segment_pool=self._segment_pool,
        )
        self._segment_watcher = SegmentWatcher(cfg, stop=self._stop)
        set_segment_watcher(self._segment_watcher)
        self._live_monitor_pool = self._heavy_pool.finalize_pool
        self._content_monitor_pool = MonitorExecutor(
            max_workers=max(cfg.monitor.executor_max_parallel, 1),
        )
        self._live_loop: LiveTickLoop | None = None
        self._slow_loop: SlowTickLoop | None = None
        self._scheduler_loop: TaskSchedulerLoop | None = None

    def start(self, *, creator_id: str | None = None) -> None:
        if not self._cfg.monitor.reconciler_enabled:
            raise ReconcilerDisabledError()
        live_poll = live_poll_interval(self._cfg)
        log.info(
            "monitor_watch_daemon_started",
            live_poll=live_poll,
            vod_poll=vod_poll_interval_sec(self._cfg),
            archive_poll=bilibili_archive_poll_sec(self._cfg),
            dynamic_poll=bilibili_dynamic_poll_sec(self._cfg),
            post_process_poll=self._cfg.live.post_process_poll_interval_sec,
            monitor_executor_parallel=self._cfg.monitor.live_worker_max_parallel,
            content_executor_parallel=self._cfg.monitor.executor_max_parallel,
            scheduler_interval_sec=self._cfg.monitor.scheduler_interval_sec,
        )
        self._live_loop = LiveTickLoop(
            self._watcher,
            self._cfg,
            creator_id=creator_id,
            stop=self._stop,
            on_tick=self._on_live_tick,
        )
        self._scheduler_loop = TaskSchedulerLoop(
            self._cfg,
            self._watcher,
            live_pool=self._live_monitor_pool,
            content_pool=self._content_monitor_pool,
            post_pool=self._post_pool,
            heavy_pool=self._heavy_pool,
            stop=self._stop,
        )
        self._segment_watcher.start()
        self._slow_loop = SlowTickLoop(
            self._watcher,
            self._cfg,
            creator_id=creator_id,
            stop=self._stop,
        )
        self._live_loop.start()
        self._scheduler_loop.start()
        self._slow_loop.start()

    def stop(self) -> None:
        self._stop.set()
        if self._live_loop is not None:
            self._live_loop.join(timeout=5.0)
        if self._scheduler_loop is not None:
            self._scheduler_loop.join(timeout=5.0)
        if self._slow_loop is not None:
            self._slow_loop.join(timeout=5.0)
        self._segment_watcher.join(timeout=5.0)
        self._content_monitor_pool.shutdown(wait=False, cancel_futures=True)
        self._post_pool.shutdown(wait=False, cancel_futures=True)
        self._heavy_pool.shutdown(wait=False, cancel_futures=True)
        set_segment_watcher(None)

    def run_single_round(self, *, creator_id: str | None = None) -> dict:
        """One LiveTick + one SchedulerTick (daemon-equivalent, no SlowTick)."""
        if not self._cfg.monitor.reconciler_enabled:
            raise ReconcilerDisabledError()
        ensure_write_gateway_started(self._cfg)
        try:
            self._watcher.ensure_session_registry()
        except Exception as exc:  # noqa: BLE001
            log.warning("single_round_session_registry_failed", error=str(exc))

        live_result = run_live_probe_tick(
            self._cfg,
            douyin=self._watcher._douyin_live,
            bilibili=self._watcher._bilibili_live,
            creator_id=creator_id,
            session_registry=self._watcher.session_registry,
        )
        if self._cfg.live.inline_decisions:
            run_live_inline_decisions(self._cfg, self._watcher)

        scheduler_loop = TaskSchedulerLoop(
            self._cfg,
            self._watcher,
            live_pool=self._live_monitor_pool,
            content_pool=self._content_monitor_pool,
            post_pool=self._post_pool,
            heavy_pool=self._heavy_pool,
            stop=self._stop,
        )
        gw = get_write_gateway(self._cfg)
        gw.write_batch(lambda conn: scheduler_loop.tick_once(conn), label="scheduler_tick")
        try:
            from media2text.core.notify.drain import drain_once

            drain_once(self._cfg, limit=20)
        except Exception:  # noqa: BLE001
            log.exception("notify_drain_single_round_failed")
        self._wait_worker_pools_idle()

        return {
            "live": live_result,
            "active_recordings": int(live_result.get("active_recordings") or 0),
            "scheduler_tick": "once",
        }

    def _wait_worker_pools_idle(self, timeout_sec: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_sec
        pools = (self._live_monitor_pool, self._content_monitor_pool)
        while time.monotonic() < deadline:
            idle = True
            for pool in pools:
                with pool._inflight_lock:
                    if pool._inflight_count > 0:
                        idle = False
                        break
            if idle:
                return
            time.sleep(0.05)
        log.warning("single_round_worker_pools_idle_timeout", timeout_sec=timeout_sec)

    def join(self, timeout: float | None = None) -> None:
        if self._live_loop is not None:
            self._live_loop.join(timeout=timeout)
        if self._scheduler_loop is not None:
            self._scheduler_loop.join(timeout=timeout)
        if self._slow_loop is not None:
            self._slow_loop.join(timeout=timeout)
