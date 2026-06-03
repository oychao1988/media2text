import threading
import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.scheduler import LiveTickLoop, MonitorScheduler, SlowTickLoop
from media2text.core.monitor.watcher import MonitorWatcher


def test_live_tick_runs_while_slow_tick_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, post_process_poll_interval_sec=60),
        monitor=MonitorConfig(vod_poll_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    post_pool = MagicMock()
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
            post_pool,
            creator_id=None,
            stop=stop,
        )
        slow_loop = SlowTickLoop(
            watcher,
            cfg,
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
        patch.object(watcher._douyin_live, "run_once", return_value={}),
        patch.object(watcher._bilibili_live, "run_once", return_value={}),
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch("media2text.core.live.scheduler.run_dynamic_tick", return_value={}),
    ):
        scheduler.start()
        time.sleep(0.2)
        scheduler.stop()
