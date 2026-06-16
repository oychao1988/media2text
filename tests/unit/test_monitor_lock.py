import json
import os
from pathlib import Path

import pytest

from media2text.core.runtime.monitor_lock import (
    clear_invalid_monitor_lock,
    is_monitor_watch_pid,
    monitor_effectively_running,
    read_lock_pid,
    write_lock_record,
)

pytestmark = pytest.mark.desktop


def test_read_lock_pid_legacy_integer(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("424242\n", encoding="utf-8")
    assert read_lock_pid(lock) == 424242


def test_read_lock_pid_json(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text(
        json.dumps({"pid": 12345, "mode": "external", "argv": "media2text monitor watch --daemon"}),
        encoding="utf-8",
    )
    assert read_lock_pid(lock) == 12345


def test_read_lock_pid_empty_file(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("", encoding="utf-8")
    assert read_lock_pid(lock) is None


def test_read_lock_pid_invalid_json(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("{}", encoding="utf-8")
    assert read_lock_pid(lock) is None


def test_is_monitor_watch_pid_matches_cmdline(monkeypatch) -> None:
    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", lambda pid: True)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._process_commandline",
        lambda pid: "/path/.venv/bin/media2text monitor watch --daemon",
    )
    assert is_monitor_watch_pid(999) is True


def test_is_monitor_watch_pid_rejects_unrelated_process(monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._process_commandline",
        lambda pid: "/usr/sbin/audioaccessoryd",
    )
    assert is_monitor_watch_pid(581) is False


def test_clear_invalid_monitor_lock_removes_mismatch(tmp_path: Path, monkeypatch) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    assert clear_invalid_monitor_lock(lock) is True
    assert not lock.exists()


def test_monitor_effectively_running_requires_heartbeat(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.config import AppConfig, LiveConfig
    from media2text.core.runtime.heartbeat import write_heartbeat

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    lock = ws / ".monitor-watch.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: True,
    )
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status={"managed_by": "none", "thread_alive": False}, live_poll_sec=10
    )
    assert running is False
    assert reason == "heartbeat_stale"


def test_monitor_effectively_running_rejects_fake_lock_regression_581(
    tmp_path: Path, monkeypatch
) -> None:
    from media2text.core.config import AppConfig, LiveConfig

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status={"managed_by": "none", "thread_alive": False}, live_poll_sec=10
    )
    assert running is False
    assert reason == "lock_pid_mismatch"


def test_monitor_effectively_running_embedded_stale_heartbeat_not_masked(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.config import AppConfig, LiveConfig
    from media2text.core.runtime.heartbeat import write_heartbeat

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    lock = ws / ".monitor-watch.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: True,
    )
    running, reason = monitor_effectively_running(
        ws,
        cfg,
        supervisor_status={"managed_by": "embedded", "thread_alive": True},
        live_poll_sec=10,
    )
    assert running is False
    assert reason == "heartbeat_stale"


def test_write_lock_record_json(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    write_lock_record(lock, pid=42, mode="embedded")
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["pid"] == 42
    assert "monitor" in data["argv"]
