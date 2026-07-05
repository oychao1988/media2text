import threading
import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.live.scheduler import LiveTickLoop, MonitorScheduler, SlowTickLoop
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher


def test_live_tick_not_blocked_by_finalize_drain(tmp_path, monkeypatch) -> None:
    """Live probe thread never invokes monitor_pool drain (TaskScheduler owns p0)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, post_process_poll_interval_sec=60),
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    order: list[str] = []
    tick_cb = MagicMock(side_effect=lambda: order.append("tick"))

    def slow_probe(*_args, **_kwargs) -> dict:
        order.append("run_once")
        return {"active_recordings": 0}

    with patch(
        "media2text.core.live.scheduler.run_live_probe_tick",
        side_effect=slow_probe,
    ):
        live_loop = LiveTickLoop(
            watcher,
            cfg,
            creator_id=None,
            stop=stop,
            on_tick=tick_cb,
        )
        live_loop.start()
        time.sleep(0.5)
        stop.set()
        live_loop.join(timeout=2)

    assert order[0] == "tick"
    assert "run_once" in order
    assert "finalize" not in order


def test_live_tick_runs_while_slow_tick_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, post_process_poll_interval_sec=60),
        monitor=MonitorConfig(vod_poll_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    run_counts: list[int] = []

    def count_probe(*_args, **_kwargs) -> dict:
        run_counts.append(1)
        return {"active_recordings": 0}

    with (
        patch(
            "media2text.core.live.scheduler.run_live_probe_tick",
            side_effect=count_probe,
        ),
        patch.object(watcher, "_run_vod_tick", side_effect=lambda **_: time.sleep(30)),
    ):
        live_loop = LiveTickLoop(
            watcher,
            cfg,
            creator_id=None,
            stop=stop,
        )
        slow_loop = SlowTickLoop(
            watcher,
            cfg,
            MagicMock(),
            creator_id=None,
            stop=stop,
        )
        live_loop.start()
        slow_loop.start()
        time.sleep(5)
        stop.set()
        live_loop.join(timeout=2)
        slow_loop.join(timeout=2)

    assert len(run_counts) >= 2


def test_slow_tick_waits_until_next_due(tmp_path, monkeypatch) -> None:
    """SlowTick sleeps until vod_due_at, not a fixed 1s loop."""
    from datetime import datetime, timedelta, timezone

    from media2text.core.storage.repos import CreatorRepo
    from media2text.core.workspace import open_db

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAslowdue",
        profile_url="https://example.com/u",
        monitor_enabled=True,
        platform="douyin",
    )
    repo.set_content_sync_enabled(cid, enabled=True)
    future = (datetime.now(timezone.utc) + timedelta(seconds=55)).isoformat()
    repo.set_vod_due(cid, future)
    conn.close()

    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    waits: list[float] = []

    def record_wait(timeout=None):
        if timeout is not None:
            waits.append(float(timeout))
        stop.set()
        return True

    stop.wait = record_wait  # type: ignore[method-assign]

    slow = SlowTickLoop(watcher, cfg, MagicMock(), creator_id=None, stop=stop)
    with (
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value={}),
    ):
        slow._run()

    assert len(waits) == 1
    assert 50.0 <= waits[0] <= 56.0


def test_monitor_scheduler_start_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    scheduler = MonitorScheduler(watcher, cfg)

    with (
        patch("media2text.core.live.probe.run_live_probe_tick", return_value={}),
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value={}),
    ):
        scheduler.start()
        time.sleep(0.2)
        scheduler.stop()


def test_finalize_enqueued_once_on_poll(tmp_path, monkeypatch) -> None:
    """Offline timeline: poll sets obs; reconcile enqueues finalize once."""
    from datetime import datetime, timedelta, timezone

    from media2text.core.live.task_reconciler import reconcile_live
    from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, offline_confirm_sec=10),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAfin",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAfin/live/x.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=999,
    )
    past_start = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    past_offline = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    conn.execute(
        """
        UPDATE live_sessions
        SET offline_since_at = ?, started_at = ?, obs_still_live = 0
        WHERE id = ?
        """,
        (past_offline, past_start, sid),
    )
    conn.commit()

    watcher = MonitorWatcher(cfg)
    core = watcher._douyin_live.core_for_conn(conn)

    with (
        patch.object(core, "_process_alive", return_value=True),
        patch.object(core, "_recording_still_live", return_value=False),
    ):
        core.poll_active_recordings()
        reconcile_live(cfg, conn)
        reconcile_live(cfg, conn)

    tasks = MonitorTaskRepo(conn).count_by_status()
    assert tasks.get("pending", 0) == 1
    row = conn.execute(
        "SELECT task_type FROM monitor_tasks WHERE status = 'pending' LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["task_type"] == "finalize"


def test_monitor_scheduler_stop_joins_before_executor_shutdown(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(scheduler_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    scheduler = MonitorScheduler(watcher, cfg)
    order: list[str] = []
    orig_join = TaskSchedulerLoop.join

    def track_scheduler_join(self, timeout=None):
        order.append("scheduler_join")
        return orig_join(self, timeout=timeout)

    orig_shutdown = MonitorExecutor.shutdown

    def track_shutdown(self, **kwargs):
        order.append("shutdown")
        return orig_shutdown(self, **kwargs)

    monkeypatch.setattr(TaskSchedulerLoop, "join", track_scheduler_join)
    monkeypatch.setattr(MonitorExecutor, "shutdown", track_shutdown)

    with (
        patch("media2text.core.live.probe.run_live_probe_tick", return_value={}),
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value={}),
    ):
        scheduler.start()
        time.sleep(0.15)
        scheduler.stop()

    assert "scheduler_join" in order
    assert "shutdown" in order
    assert order.index("scheduler_join") < order.index("shutdown")


def test_monitor_executor_submit_after_shutdown_returns_false() -> None:
    pool = MonitorExecutor(max_workers=1)
    pool.shutdown(wait=False, cancel_futures=True)
    assert pool.submit(
        AppConfig(workspace="/tmp/unused"),
        task_id="task-1",
        notify=MagicMock(),
    ) is False
