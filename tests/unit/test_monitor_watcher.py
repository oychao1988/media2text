import signal
import threading
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.monitor.watcher import MonitorWatcher, _graceful_stop_event


def test_run_once_calls_reconcile_without_watcher_kwarg(tmp_path, monkeypatch) -> None:
    """MH-4 run_once must not pass watcher= to reconcile_* (signature mismatch)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    watcher = MonitorWatcher(cfg)
    empty = {"errors": [], "auth_required": False, "platform_changed": False}
    with (
        patch.object(watcher._douyin_live, "run_once", return_value={"active": 0, **empty}),
        patch.object(watcher._bilibili_live, "run_once", return_value={"active": 0, **empty}),
        patch.object(watcher, "_run_vod_tick", return_value=empty),
        patch.object(watcher, "_run_archive_tick", return_value=empty),
        patch.object(watcher, "_run_dynamic_tick", return_value=empty),
        patch("media2text.core.live.task_reconciler.reconcile_live") as reconcile_live,
        patch("media2text.core.live.task_reconciler.reconcile_content") as reconcile_content,
    ):
        result = watcher.run_once()

    reconcile_live.assert_called_once_with(cfg, watcher._conn)
    reconcile_content.assert_called_once_with(cfg, watcher._conn)
    assert result["errors"] == []


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
        ),
        patch(
            "media2text.core.monitor.watcher._graceful_stop_event",
            return_value=stop,
        ),
    ):
        watcher.run_daemon(creator_id="c1")

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
