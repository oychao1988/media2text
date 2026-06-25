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
    assert cfg.monitor.reconciler_enabled is True
    assert cfg.monitor.reconciler_log_only is False
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
        live_pool=pool,
        content_pool=MagicMock(),
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


def test_slow_tick_uses_own_conn_not_watcher_conn(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(scheduler_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    shared_conn_ids: set[int] = {id(watcher._conn)}
    slow_conn_ids: list[int] = []

    orig_open = open_db

    def tracking_open_db(c):
        conn = orig_open(c)
        if threading.current_thread().name == "slow-tick":
            slow_conn_ids.append(id(conn))
        return conn

    monkeypatch.setattr("media2text.core.live.scheduler.open_db", tracking_open_db)
    monkeypatch.setattr(
        "media2text.core.live.probe.run_live_probe_tick",
        lambda *a, **k: {},
    )

    scheduler = MonitorScheduler(watcher, cfg)
    scheduler.start()
    time.sleep(2.5)
    scheduler.stop()

    assert slow_conn_ids, "slow-tick thread should open_db"
    assert shared_conn_ids.isdisjoint(set(slow_conn_ids))


def test_probe_workers_prefers_probe_parallelism(tmp_path) -> None:
    from media2text.core.live.probe import probe_workers

    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(scan_concurrency=2),
        monitor=MonitorConfig(probe_parallelism=6),
    )
    assert probe_workers(cfg, 10) == 2
    assert probe_workers(cfg, 3) == 2


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


def test_scheduler_tick_order_reconcile_before_drain(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    calls: list[str] = []
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(
        side_effect=lambda *a, **k: calls.append("drain") or 0
    )
    pool.drain_pending = MagicMock()
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=MagicMock(),
        post_pool=MagicMock(),
        stop=stop,
    )

    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(
        task_scheduler_mod,
        "reconcile_live",
        lambda *a, **k: calls.append("live") or 0,
    )
    monkeypatch.setattr(
        task_scheduler_mod,
        "reconcile_content",
        lambda *a, **k: calls.append("content") or 0,
    )
    loop.tick_once(conn)
    assert calls.index("live") < calls.index("drain")
    assert calls.index("content") < calls.index("drain")


def test_scheduler_tick_order_post_process_before_content(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    order: list[str] = []
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)

    def track_drain(*args, **kwargs):
        min_priority = kwargs.get("min_priority", 10)
        if min_priority >= 10:
            order.append("content")
        else:
            order.append("live")
        return 0

    pool.drain_pending = MagicMock(side_effect=track_drain)
    post_pool = MagicMock()
    post_pool.drain_pending = MagicMock(side_effect=lambda *a, **k: order.append("post"))
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=pool,
        post_pool=post_pool,
        stop=stop,
    )

    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    loop.tick_once(conn)
    assert order.index("post") < order.index("content")


def test_task_scheduler_defers_post_process_when_live_pending(
    tmp_path, monkeypatch
) -> None:
    from unittest.mock import MagicMock
    import threading

    from media2text.core.config import MonitorConfig
    from media2text.core.live.task_scheduler import TaskSchedulerLoop
    from media2text.core.monitor.watcher import MonitorWatcher
    from media2text.core.workspace import open_db

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAdeferpp",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="prepare_live_recording",
        dedupe_key=f"prepare:{cid}",
        priority=1,
    )
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    post_pool = MagicMock()
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=pool,
        post_pool=post_pool,
        stop=stop,
    )
    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    loop.tick_once(conn)
    post_pool.drain_pending.assert_not_called()


def test_scheduler_content_drain_excludes_recording_creator(
    tmp_path, monkeypatch
) -> None:
    from media2text.core.storage.repos import LiveSessionRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    cid_a = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAArecA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAArecB",
        profile_url="https://example.com/b",
        monitor_enabled=True,
    )
    LiveSessionRepo(conn).create(
        creator_id=cid_a,
        room_id="1",
        temp_path=str(tmp_path / "a.flv"),
        ffmpeg_pid=1,
    )
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    content_pool = MagicMock()
    drain_kwargs: dict = {}

    def capture_content_drain(*args, **kwargs):
        drain_kwargs.update(kwargs)
        return 0

    content_pool.drain_pending = MagicMock(side_effect=capture_content_drain)
    post_pool = MagicMock()
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=content_pool,
        post_pool=post_pool,
        stop=stop,
    )
    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    loop.tick_once(conn)
    assert drain_kwargs.get("limit") == cfg.monitor.executor_max_parallel
    assert drain_kwargs.get("limit") != 0
    assert cid_a in drain_kwargs.get("exclude_creator_ids", frozenset())


def test_scheduler_releases_only_recording_creator_running_content(
    tmp_path, monkeypatch
) -> None:
    from media2text.core.storage.repos import LiveSessionRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    cid_a = creators.add(
        sec_uid="MS4wLjABAAAArelA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    cid_b = creators.add(
        sec_uid="MS4wLjABAAAArelB",
        profile_url="https://example.com/b",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    task_a = repo.enqueue(
        creator_id=cid_a,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid_a}",
        priority=10,
    )
    task_b = repo.enqueue(
        creator_id=cid_b,
        task_type="download",
        dedupe_key=f"download:{cid_b}",
        priority=10,
    )
    assert task_a is not None
    assert task_b is not None
    repo.claim_pending(limit=2, min_priority=10)
    LiveSessionRepo(conn).create(
        creator_id=cid_a,
        room_id="1",
        temp_path=str(tmp_path / "a.flv"),
        ffmpeg_pid=1,
    )
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    content_pool = MagicMock()
    content_pool.drain_pending = MagicMock(return_value=0)
    post_pool = MagicMock()
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=content_pool,
        post_pool=post_pool,
        stop=stop,
    )
    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    loop.tick_once(conn)
    assert repo.get(task_a).status == "pending"
    assert repo.get(task_b).status == "running"


def test_content_drain_claims_other_creator_while_recording(
    tmp_path, monkeypatch
) -> None:
    from media2text.core.storage.repos import LiveSessionRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    cid_a = creators.add(
        sec_uid="MS4wLjABAAAAclaimA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    cid_b = creators.add(
        sec_uid="MS4wLjABAAAAclaimB",
        profile_url="https://example.com/b",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    sync_a = repo.enqueue(
        creator_id=cid_a,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid_a}",
        priority=10,
    )
    sync_b = repo.enqueue(
        creator_id=cid_b,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid_b}",
        priority=10,
    )
    assert sync_a is not None
    assert sync_b is not None
    LiveSessionRepo(conn).create(
        creator_id=cid_a,
        room_id="1",
        temp_path=str(tmp_path / "a.flv"),
        ffmpeg_pid=1,
    )
    pool = MonitorExecutor(max_workers=1)
    watcher = MonitorWatcher(cfg)
    pool.submit = MagicMock()  # type: ignore[method-assign]
    pool.drain_pending(
        cfg,
        conn,
        notify=watcher._notify,
        watcher=watcher,
        limit=1,
        min_priority=10,
        exclude_creator_ids=frozenset({cid_a}),
    )
    assert repo.get(sync_a).status == "pending"
    assert repo.get(sync_b).status == "running"
    pool.shutdown(wait=False)

