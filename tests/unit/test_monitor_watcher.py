from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.monitor.watcher import MonitorWatcher


def test_run_daemon_delegates_to_scheduler(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=17),
    )
    watcher = MonitorWatcher(cfg)
    mock_scheduler = MagicMock()

    with (
        patch("media2text.core.monitor.watcher.workspace_lock"),
        patch(
            "media2text.core.monitor.watcher.MonitorScheduler",
            return_value=mock_scheduler,
        ),
        patch("media2text.core.monitor.watcher.time.sleep", side_effect=KeyboardInterrupt),
    ):
        try:
            watcher.run_daemon(creator_id="c1")
        except KeyboardInterrupt:
            pass

    mock_scheduler.start.assert_called_once_with(creator_id="c1")
    mock_scheduler.stop.assert_called_once()
