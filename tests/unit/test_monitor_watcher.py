from unittest.mock import patch

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.monitor.watcher import MonitorWatcher


def test_run_daemon_uses_live_poll_interval(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=17),
    )
    watcher = MonitorWatcher(cfg)
    sleeps: list[float] = []

    def fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        raise KeyboardInterrupt

    with (
        patch("media2text.core.monitor.watcher.workspace_lock"),
        patch("media2text.core.monitor.watcher.time.sleep", side_effect=fake_sleep),
        patch.object(watcher._douyin_live, "run_once"),
        patch.object(watcher._bilibili_live, "run_once"),
        patch("media2text.core.monitor.watcher.drain_pending_jobs"),
    ):
        try:
            watcher.run_daemon()
        except KeyboardInterrupt:
            pass

    assert 17 in sleeps
