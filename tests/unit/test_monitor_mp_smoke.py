"""Automated replacements for TODOS.md Monitor DB Contention manual smoke (MP-smoke 1–4)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from media2text.api.app import create_app, lifespan
from media2text.api.deps import get_cfg, get_db
from media2text.api.services.health import clear_health_cache
from media2text.core.config import AppConfig, DesktopConfig, MonitorConfig
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.runtime.heartbeat import write_heartbeat
from media2text.core.runtime.monitor_lock import is_monitor_watch_pid, read_lock_pid
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo, MonitorTaskRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _minimal_config_yaml(workspace: Path) -> str:
    return f"""\
workspace: {workspace}
monitor:
  reconciler_enabled: true
  scheduler_interval_sec: 2
  live_poll_interval_sec: 30
  stale_running_sec: 3600
desktop:
  auto_start_monitor: true
  monitor_self_heal: false
live:
  pipeline_mode: legacy
  transcribe_on_complete: false
"""


def _media2text_bin() -> str:
    found = shutil.which("media2text")
    if found:
        return found
    candidate = Path(sys.executable).parent / "media2text"
    if candidate.is_file():
        return str(candidate)
    pytest.skip("media2text CLI not on PATH")


def test_mp_smoke_cli_daemon_process_and_lock(tmp_path) -> None:
    """TODOS #1: bin/monitor-watch-daemon.sh / CLI --daemon holds lock + live PID."""
    data = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_minimal_config_yaml(data), encoding="utf-8")
    env = os.environ.copy()
    env["MEDIA2TEXT_CONFIG"] = str(cfg_path)
    proc = subprocess.Popen(
        [_media2text_bin(), "monitor", "watch", "--daemon"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8.0
        lock = data / ".monitor-watch.lock"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = (proc.stdout.read() if proc.stdout else "") + (
                    proc.stderr.read() if proc.stderr else ""
                )
                pytest.fail(f"daemon exited early (code={proc.returncode}): {out}")
            if lock.is_file():
                pid = read_lock_pid(lock)
                if pid is not None and is_monitor_watch_pid(pid):
                    break
            time.sleep(0.25)
        else:
            pytest.fail("daemon lock never became valid monitor-watch PID")

        assert proc.poll() is None
        pid = read_lock_pid(lock)
        assert pid is not None
        assert is_monitor_watch_pid(pid)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _api_client_for_cfg(cfg: AppConfig, monkeypatch) -> TestClient:
    clear_health_cache()
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    ws = cfg.ensure_workspace()
    monkeypatch.setattr(
        "media2text.core.logging.enable_monitor_log_sink",
        lambda _ws: ws / "monitor-watch.log",
    )
    app = create_app()
    api = app.state.api_app

    def override_cfg() -> AppConfig:
        return cfg

    def override_db():
        conn = open_db(cfg)
        try:
            yield conn
        finally:
            conn.close()

    for target in (app, api):
        target.dependency_overrides[get_cfg] = override_cfg
        target.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_mp_smoke_runtime_external_when_cli_lock(tmp_path, monkeypatch) -> None:
    """Desktop serve startup skips embedded when external CLI daemon is running."""
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=False),
    )
    ws = cfg.ensure_workspace()
    external_pid = 424242
    (ws / ".monitor-watch.lock").write_text(
        json.dumps(
            {
                "pid": external_pid,
                "mode": "external",
                "argv": "media2text monitor watch --daemon",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_embedded_monitor_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._pid_alive",
        lambda pid: pid == external_pid,
    )
    write_heartbeat(ws, last_tick_at=datetime.now(timezone.utc).isoformat())

    sup = MagicMock()
    sup.status_dict.return_value = {
        "managed_by": "external",
        "thread_alive": False,
        "running": True,
        "pid": external_pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_tick_at": datetime.now(timezone.utc).isoformat(),
    }
    sup.stop.return_value = {"ok": True, "stopped": True}

    clear_health_cache()
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.logging.enable_monitor_log_sink",
        lambda _ws: ws / "monitor-watch.log",
    )
    app = create_app()
    api = app.state.api_app
    api.state.supervisor = sup

    def override_cfg() -> AppConfig:
        return cfg

    def override_db():
        conn = open_db(cfg)
        try:
            yield conn
        finally:
            conn.close()

    for target in (app, api):
        target.dependency_overrides[get_cfg] = override_cfg
        target.dependency_overrides[get_db] = override_db

    with (
        patch("media2text.api.app.MonitorSupervisor", return_value=sup),
        patch(
            "media2text.api.services.work_queue.recover_stale_work",
            return_value={"ok": True},
        ),
        TestClient(app) as client,
    ):
        body = client.get("/api/runtime").json()

    assert body["ok"] is True
    assert body["managed_by"] == "external"
    assert body["health"] == "healthy"
    assert body["daemon"]["running"] is True
    sup.takeover.assert_not_called()
    sup.start.assert_not_called()


def test_mp_smoke_runtime_embedded_without_external_cli(tmp_path, monkeypatch) -> None:
    """TODOS #3: no external CLI lock → GET /api/runtime reports embedded."""
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=False),
    )
    ws = cfg.ensure_workspace()
    write_heartbeat(ws, last_tick_at=datetime.now(timezone.utc).isoformat())

    sup = MagicMock()
    sup.status_dict.return_value = {
        "managed_by": "embedded",
        "thread_alive": True,
        "running": True,
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_tick_at": datetime.now(timezone.utc).isoformat(),
    }

    clear_health_cache()
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.logging.enable_monitor_log_sink",
        lambda _ws: ws / "monitor-watch.log",
    )
    app = create_app()
    api = app.state.api_app
    api.state.supervisor = sup

    def override_cfg() -> AppConfig:
        return cfg

    def override_db():
        conn = open_db(cfg)
        try:
            yield conn
        finally:
            conn.close()

    for target in (app, api):
        target.dependency_overrides[get_cfg] = override_cfg
        target.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        body = client.get("/api/runtime").json()

    assert body["managed_by"] == "embedded"
    assert body["daemon"]["running"] is True


@pytest.mark.asyncio
async def test_mp_smoke_lifespan_auto_starts_embedded_without_cli(tmp_path, monkeypatch) -> None:
    """TODOS #3 (lifespan): Desktop sidecar auto_start_monitor with no lock."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=False),
    )
    cfg.ensure_workspace()
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)

    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    sup.start.return_value = {"ok": True, "managed_by": "embedded"}
    sup.stop.return_value = {"ok": True, "stopped": True}

    app = FastAPI()
    with ExitStack() as stack:
        stack.enter_context(patch("media2text.api.app.run_drain_loop", new=AsyncMock()))
        stack.enter_context(patch("media2text.api.app.run_notify_drain_loop", new=AsyncMock()))
        stack.enter_context(patch("media2text.api.app.run_runtime_health_loop", new=AsyncMock()))
        stack.enter_context(patch("media2text.api.app.MonitorSupervisor", return_value=sup))
        async with lifespan(app):
            pass

    sup.start.assert_called_once_with(cfg)


def test_mp_smoke_live_lane_defers_post_process_and_drains_prepare(
    tmp_path, monkeypatch
) -> None:
    """TODOS #4: live lane backlog defers post_process; prepare_live_recording drains."""
    import threading

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAmpSmoke",
        profile_url="https://example.com/mp-smoke",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="room-smoke")
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="prepare_live_recording",
        dedupe_key=f"prepare:{cid}",
        priority=1,
    )

    watcher = MonitorWatcher(cfg)
    live_pool = MagicMock()
    live_pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    live_pool.drain_pending = MagicMock(return_value=1)
    content_pool = MagicMock()
    content_pool.drain_pending = MagicMock(return_value=0)
    post_pool = MagicMock()
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=live_pool,
        content_pool=content_pool,
        post_pool=post_pool,
        stop=stop,
    )

    logged: list[tuple[str, dict]] = []

    def capture_info(event: str, **kwargs: object) -> None:
        logged.append((event, kwargs))

    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod.log, "info", capture_info)

    loop.tick_once(conn)

    defer = [(e, kw) for e, kw in logged if e == "post_process_deferred_for_live_lane"]
    assert defer, f"expected defer log, got {logged}"
    assert int(defer[0][1]["count"]) >= 1
    post_pool.drain_pending.assert_not_called()
    live_pool.drain_pending.assert_called_once()
    call_kw = live_pool.drain_pending.call_args.kwargs
    assert call_kw["min_priority"] == 1
    assert call_kw["max_priority"] == 9
    content_pool.drain_pending.assert_called_once()
    conn.close()
