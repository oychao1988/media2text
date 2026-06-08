import threading
import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.live.scheduler import LiveTickLoop, MonitorScheduler
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo
from media2text.core.workspace import open_db


def test_monitor_scheduler_config_defaults() -> None:
    cfg = AppConfig()
    assert cfg.monitor.scheduler_interval_sec == 1
    assert cfg.monitor.live_lane_min_claim_per_tick == 1
    assert cfg.monitor.probe_parallelism == 4
    assert cfg.monitor.reconciler_enabled is False
    assert cfg.monitor.live_worker_max_parallel == 1


def test_task_scheduler_drains_priority_zero_async(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAx",
        profile_url="https://x",
        monitor_enabled=True,
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="finalize",
        dedupe_key="finalize:s1",
        priority=0,
        payload_json='{"session_id":"s1"}',
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    pool = MagicMock()
    submitted: list[str] = []

    def capture_submit(*args, **kwargs):
        submitted.append(kwargs.get("task_id", ""))

    pool.claim_and_submit_priority_zero = MagicMock(side_effect=capture_submit)

    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        pool,
        post_pool=MagicMock(),
        stop=stop,
    )
    loop.tick_once(conn)
    assert len(submitted) >= 1
    pool.claim_and_submit_priority_zero.assert_called()


def test_live_tick_not_blocked_by_slow_finalize(tmp_path, monkeypatch) -> None:
    """LiveTick must not call sync drain_priority_zero (finalize runs on Scheduler)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, post_process_poll_interval_sec=60),
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()

    def slow_run_once(**_kwargs) -> dict:
        time.sleep(0.3)
        return {}

    with (
        patch.object(watcher._douyin_live, "run_once", side_effect=slow_run_once),
        patch.object(watcher._bilibili_live, "run_once", return_value={}),
    ):
        live_loop = LiveTickLoop(
            watcher,
            cfg,
            creator_id=None,
            stop=stop,
        )
        t0 = time.monotonic()
        live_loop.start()
        time.sleep(0.15)
        stop.set()
        live_loop.join(timeout=2)

    assert time.monotonic() - t0 < 1.0


def test_conn_per_thread_no_shared_watcher_conn(tmp_path, monkeypatch) -> None:
    """Probe and Scheduler each open_db; no cross-thread writes on watcher._conn."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(scheduler_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    shared_conn_ids: set[int] = {id(watcher._conn)}
    probe_conn_ids: list[int] = []
    scheduler_conn_ids: list[int] = []

    orig_open = open_db

    def tracking_open_db(c):
        conn = orig_open(c)
        tid = threading.current_thread().name
        if tid == "live-probe":
            probe_conn_ids.append(id(conn))
        elif tid == "task-scheduler":
            scheduler_conn_ids.append(id(conn))
        return conn

    monkeypatch.setattr("media2text.core.live.scheduler.open_db", tracking_open_db)
    monkeypatch.setattr("media2text.core.live.task_scheduler.open_db", tracking_open_db)
    monkeypatch.setattr(
        "media2text.core.live.probe.run_live_probe_tick",
        lambda *a, **k: {},
    )

    scheduler = MonitorScheduler(watcher, cfg)
    with (
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value={}),
    ):
        scheduler.start()
        time.sleep(2.5)
        scheduler.stop()

    assert probe_conn_ids, "live-probe thread should open_db"
    assert scheduler_conn_ids, "task-scheduler thread should open_db"
    assert shared_conn_ids.isdisjoint(set(probe_conn_ids))
    assert shared_conn_ids.isdisjoint(set(scheduler_conn_ids))


def test_probe_tick_respects_budget(tmp_path, monkeypatch) -> None:
    from media2text.core.live.probe import probe_budget_sec, run_live_probe_tick

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(probe_tick_budget_sec=1),
    )
    conn = open_db(cfg)
    watcher = MonitorWatcher(cfg)

    def slow_douyin(**kwargs):
        deadline = kwargs.get("deadline")
        end = deadline if deadline is not None else time.monotonic() + 2
        while time.monotonic() < end:
            time.sleep(0.05)
        return {"active": 0}

    with (
        patch.object(watcher._douyin_live, "run_once", side_effect=slow_douyin),
        patch.object(watcher._bilibili_live, "run_once", return_value={"skipped": "budget_exhausted"}),
    ):
        t0 = time.monotonic()
        run_live_probe_tick(
            cfg,
            conn,
            douyin=watcher._douyin_live,
            bilibili=watcher._bilibili_live,
        )
        elapsed = time.monotonic() - t0

    assert elapsed < probe_budget_sec(cfg) + 0.5


def test_claim_and_submit_priority_zero_async(tmp_path, monkeypatch) -> None:
    """MonitorExecutor submits p0 tasks to thread pool instead of inline drain."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAy",
        profile_url="https://y",
        monitor_enabled=True,
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="finalize",
        dedupe_key="finalize:s2",
        priority=0,
        payload_json='{"session_id":"s2"}',
    )
    pool = MonitorExecutor(max_workers=1)
    watcher = MonitorWatcher(cfg)
    submitted: list[str] = []

    orig_submit = pool.submit

    def track_submit(cfg, *, task_id, notify, watcher=None):
        submitted.append(task_id)

    pool.submit = track_submit  # type: ignore[method-assign]
    count = pool.claim_and_submit_priority_zero(
        cfg,
        conn,
        notify=watcher._notify,
        watcher=watcher,
        limit=1,
    )
    time.sleep(0.2)
    assert count == 1
    assert len(submitted) == 1
    pool.shutdown(wait=False)
