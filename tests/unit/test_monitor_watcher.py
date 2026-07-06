import signal
import threading
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher, _graceful_stop_event


def test_monitor_watch_single_round_matches_daemon_tick(tmp_path, monkeypatch) -> None:
    """Non-daemon run_once must use run_live_probe_tick + TaskSchedulerLoop.tick_once."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    watcher = MonitorWatcher(cfg)
    probe_kwargs: list[dict] = []
    scheduler_ticks: list[object] = []

    def track_probe(*_args, **kwargs) -> dict:
        probe_kwargs.append(kwargs)
        return {"active_recordings": 0, "douyin": {}, "bilibili": {}}

    def track_scheduler_tick(_self, conn) -> None:
        scheduler_ticks.append(conn)

    with (
        patch("media2text.core.live.scheduler.run_live_probe_tick", side_effect=track_probe),
        patch.object(TaskSchedulerLoop, "tick_once", track_scheduler_tick),
        patch.object(watcher._douyin_live, "run_once") as dy_run_once,
        patch.object(watcher._bilibili_live, "run_once") as bi_run_once,
        patch("media2text.core.notify.drain.drain_once"),
    ):
        result = watcher.run_once()

    assert len(probe_kwargs) == 1
    assert probe_kwargs[0]["session_registry"] is watcher.session_registry
    assert len(scheduler_ticks) == 1
    dy_run_once.assert_not_called()
    bi_run_once.assert_not_called()
    assert result["scheduler_tick"] == "once"
    assert result["live"]["active_recordings"] == 0


def test_run_daemon_delegates_to_scheduler(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=17),
    )
    watcher = MonitorWatcher(cfg)
    mock_scheduler = MagicMock()
    stop = threading.Event()
    stop.set()

    with (
        patch("media2text.core.monitor.watcher.workspace_lock"),
        patch(
            "media2text.core.monitor.watcher.MonitorScheduler",
            return_value=mock_scheduler,
        ) as scheduler_cls,
        patch(
            "media2text.core.monitor.watcher._graceful_stop_event",
            return_value=stop,
        ),
    ):
        watcher.run_daemon(creator_id="c1")

    scheduler_cls.assert_called_once()
    assert scheduler_cls.call_args.kwargs["stop"] is stop
    mock_scheduler.start.assert_called_once_with(creator_id="c1")
    mock_scheduler.stop.assert_called_once()


def test_graceful_stop_event_sigterm_sets_event(monkeypatch) -> None:
    installed: dict[int, object] = {}

    def fake_signal(sig, handler):
        installed[sig] = handler
        return handler

    monkeypatch.setattr(signal, "signal", fake_signal)
    stop = _graceful_stop_event(None)
    assert not stop.is_set()
    installed[signal.SIGTERM](signal.SIGTERM, None)
    assert stop.is_set()


def test_graceful_stop_event_reuses_supervisor_event() -> None:
    existing = threading.Event()
    assert _graceful_stop_event(existing) is existing


def test_run_daemon_cli_stop_triggers_scheduler_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=17),
    )
    watcher = MonitorWatcher(cfg)
    mock_scheduler = MagicMock()
    ready = threading.Event()
    cli_stop = threading.Event()

    def _start(**_kwargs) -> None:
        ready.set()

    mock_scheduler.start.side_effect = _start

    def _fake_graceful_stop(existing: threading.Event | None) -> threading.Event:
        assert existing is None
        return cli_stop

    with (
        patch("media2text.core.monitor.watcher.workspace_lock"),
        patch(
            "media2text.core.monitor.watcher.MonitorScheduler",
            return_value=mock_scheduler,
        ),
        patch(
            "media2text.core.monitor.watcher._graceful_stop_event",
            side_effect=_fake_graceful_stop,
        ),
    ):
        thread = threading.Thread(target=watcher.run_daemon, daemon=True)
        thread.start()
        assert ready.wait(timeout=2.0)
        cli_stop.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    mock_scheduler.stop.assert_called_once()
