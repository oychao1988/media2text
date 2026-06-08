import threading
import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.scheduler import LiveTickLoop, MonitorScheduler, SlowTickLoop
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

    def slow_run_once(**_kwargs) -> dict:
        order.append("run_once")
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

    def count_run_once(**_kwargs) -> dict:
        run_counts.append(1)
        return {}

    with (
        patch.object(watcher._douyin_live, "run_once", side_effect=count_run_once),
        patch.object(watcher._bilibili_live, "run_once", return_value={}),
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
    core = watcher._douyin_live._core

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
