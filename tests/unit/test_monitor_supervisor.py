import json
import threading
from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.runtime.supervisor import MonitorSupervisor

pytestmark = pytest.mark.desktop


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(vod_poll_interval_sec=60),
    )


def test_supervisor_start_stop_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    sup = MonitorSupervisor()
    hold = threading.Event()
    hold.set()

    def _hold_thread(self) -> None:
        hold.clear()
        hold.wait(timeout=2.0)

    with patch.object(MonitorSupervisor, "_run_daemon_thread", _hold_thread):
        first = sup.start(cfg)
        assert first["ok"] is True
        hold.wait(timeout=1.0)
        second = sup.start(cfg)
        assert second["ok"] is False
        assert second["already_running"] is True
        hold.set()
        stop = sup.stop(timeout_sec=2.0)
        assert stop["ok"] is True
        assert stop["stopped"] is True
        again = sup.stop()
        assert again["stopped"] is False


def test_supervisor_external_lock_blocks_start(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 424242
    (ws / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")
    sup = MonitorSupervisor()

    def _alive(pid: int) -> bool:
        return pid == external_pid

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", _alive)
    monkeypatch.setattr(
        "media2text.core.runtime.supervisor.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    result = sup.start(cfg)
    assert result["ok"] is False
    assert result["already_running_external"] is True
    assert result["pid"] == external_pid


def test_supervisor_record_tick_writes_heartbeat(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    sup = MonitorSupervisor()
    sup._cfg = cfg
    sup.record_tick()
    heartbeat = cfg.ensure_workspace() / ".runtime-heartbeat"
    assert heartbeat.is_file()
    data = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert "last_tick_at" in data
    status = sup.status(cfg)
    assert status.last_tick_at == data["last_tick_at"]


def test_supervisor_stop_not_owner_for_external(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 515151
    (ws / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")
    sup = MonitorSupervisor()

    def _alive(pid: int) -> bool:
        return pid == external_pid

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", _alive)
    monkeypatch.setattr(
        "media2text.core.runtime.supervisor.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    result = sup.stop(cfg)
    assert result["ok"] is False
    assert result["not_owner"] is True


def test_supervisor_stop_external_and_takeover(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 616161
    (ws / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")
    sup = MonitorSupervisor()
    alive = {external_pid}

    def fake_alive(pid: int) -> bool:
        return pid in alive

    def fake_kill(pid: int, sig: int) -> None:
        alive.discard(pid)

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", fake_alive)
    monkeypatch.setattr(
        "media2text.core.runtime.supervisor.is_monitor_watch_pid",
        fake_alive,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        fake_alive,
    )
    monkeypatch.setattr("media2text.core.runtime.supervisor._pid_alive", fake_alive)
    monkeypatch.setattr("media2text.core.runtime.supervisor.os.kill", fake_kill)

    stop_result = sup.stop_external(cfg)
    assert stop_result["ok"] is True
    assert stop_result["stopped"] is True

    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        takeover = sup.takeover(cfg)
    assert takeover["ok"] is True
    assert takeover["start"]["managed_by"] == "embedded"


def test_supervisor_start_clears_fake_external_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    sup = MonitorSupervisor()
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        result = sup.start(cfg)
    assert result["ok"] is True


def test_supervisor_repair_embedded_lock_and_takeover(tmp_path, monkeypatch) -> None:
    import json
    import os
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    sup = MonitorSupervisor()
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = True
    sup._thread = fake_thread
    sup._lock_path = ws / ".monitor-watch.lock"
    sup._lock_fd = -1
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    takeover = sup.takeover(cfg)
    assert takeover["ok"] is True
    assert takeover["repair"]["action"] == "repair_embedded_lock"
    lock = json.loads((ws / ".monitor-watch.lock").read_text(encoding="utf-8"))
    assert lock["pid"] == os.getpid()
    assert lock["mode"] == "embedded"


def test_supervisor_takeover_restarts_stale_embedded(tmp_path, monkeypatch) -> None:
    import os
    from unittest.mock import MagicMock

    from media2text.core.runtime.monitor_lock import write_lock_record

    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    sup = MonitorSupervisor()
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = True
    sup._thread = fake_thread
    sup._lock_path = ws / ".monitor-watch.lock"
    sup._lock_fd = -1
    write_lock_record(ws / ".monitor-watch.lock", pid=os.getpid(), mode="embedded")

    stop_calls: list[dict] = []

    def fake_stop(self, cfg, *, timeout_sec=10.0):
        stop_calls.append({"timeout_sec": timeout_sec})
        self._thread = None
        self._lock_fd = None
        self._lock_path = None
        return {"ok": True, "stopped": True, "managed_by": "embedded"}

    monkeypatch.setattr(MonitorSupervisor, "stop", fake_stop)

    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        takeover = sup.takeover(cfg)

    assert stop_calls
    assert takeover["ok"] is True
    assert takeover["start"]["managed_by"] == "embedded"


def test_supervisor_reset_stale_only_releases_recording_creator_content(
    tmp_path, monkeypatch
) -> None:
    from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo
    from media2text.core.workspace import open_db

    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    cid_a = creators.add(
        sec_uid="MS4wLjABAAAAsupA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    cid_b = creators.add(
        sec_uid="MS4wLjABAAAAsupB",
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
    conn.close()

    sup = MonitorSupervisor()
    sup._reset_stale_queue_work(cfg)

    conn2 = open_db(cfg)
    repo2 = MonitorTaskRepo(conn2)
    assert repo2.get(task_a).status == "pending"
    assert repo2.get(task_b).status == "running"
    conn2.close()
