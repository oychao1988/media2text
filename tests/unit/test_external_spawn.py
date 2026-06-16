import pytest

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.runtime.external_spawn import spawn_cli_monitor_daemon

pytestmark = pytest.mark.desktop


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(vod_poll_interval_sec=60),
    )


def test_spawn_cli_monitor_daemon_waits_for_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    spawned_pid = 777777

    class FakeProc:
        pid = 888888

        def poll(self):
            return None

    def fake_popen(*args, **kwargs):
        (ws / ".monitor-watch.lock").write_text(str(spawned_pid), encoding="utf-8")
        return FakeProc()

    monkeypatch.setattr(
        "media2text.core.runtime.external_spawn.subprocess.Popen",
        fake_popen,
    )

    def _alive(pid: int) -> bool:
        return pid == spawned_pid

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", _alive)
    monkeypatch.setattr(
        "media2text.core.runtime.external_spawn.is_monitor_watch_pid",
        _alive,
    )
    result = spawn_cli_monitor_daemon(cfg, wait_sec=2.0)
    assert result["ok"] is True
    assert result["pid"] == spawned_pid
    assert result["managed_by"] == "external"


def test_spawn_blocks_when_external_already_running(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 424242
    (ws / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")

    def _alive(pid: int) -> bool:
        return pid == external_pid

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", _alive)
    monkeypatch.setattr(
        "media2text.core.runtime.external_spawn.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    result = spawn_cli_monitor_daemon(cfg)
    assert result["ok"] is False
    assert result["already_running_external"] is True
