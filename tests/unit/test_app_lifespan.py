import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from media2text.api.app import lifespan
from media2text.core.config import AppConfig, DesktopConfig

pytestmark = pytest.mark.desktop


def _cfg(tmp_path, *, auto_start: bool = True) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=auto_start, monitor_self_heal=False),
    )


def _enter_lifespan_patches(stack: ExitStack, *, supervisor: MagicMock):
    stack.enter_context(patch("media2text.api.app.run_drain_loop", new=AsyncMock()))
    stack.enter_context(patch("media2text.api.app.run_notify_drain_loop", new=AsyncMock()))
    stack.enter_context(patch("media2text.api.app.run_runtime_health_loop", new=AsyncMock()))
    stack.enter_context(patch("media2text.api.app.MonitorSupervisor", return_value=supervisor))


@pytest.mark.asyncio
async def test_lifespan_skips_external_monitor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 424242
    (ws / ".monitor-watch.lock").write_text(
        json.dumps({"pid": external_pid, "mode": "external", "argv": "media2text monitor watch --daemon"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_embedded_monitor_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._pid_alive",
        lambda pid: pid == external_pid,
    )
    app = FastAPI()
    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    with ExitStack() as stack:
        _enter_lifespan_patches(stack, supervisor=sup)
        stack.enter_context(
            patch(
                "media2text.core.runtime.monitor_startup.monitor_owner_status",
                return_value={
                    "running": True,
                    "managed_by": "external",
                    "pid": external_pid,
                },
            )
        )
        async with lifespan(app):
            pass
    sup.takeover.assert_not_called()
    sup.start.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_defers_embedded_monitor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    embedded_pid = 515151
    (ws / ".monitor-watch.lock").write_text(
        json.dumps({"pid": embedded_pid, "mode": "embedded", "argv": "media2text serve"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_embedded_monitor_pid",
        lambda pid: pid == embedded_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._pid_alive",
        lambda pid: pid == embedded_pid,
    )
    app = FastAPI()
    sup = MagicMock()
    sup.stop.return_value = {"ok": True, "stopped": False}
    with ExitStack() as stack:
        _enter_lifespan_patches(stack, supervisor=sup)
        async with lifespan(app):
            pass
    sup.start.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_starts_embedded_when_no_monitor(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    app = FastAPI()
    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    sup.status_dict.return_value = {"thread_alive": False}
    sup.start.return_value = {"ok": True, "managed_by": "embedded"}
    sup.stop.return_value = {"ok": True, "stopped": True}
    with ExitStack() as stack:
        _enter_lifespan_patches(stack, supervisor=sup)
        stack.enter_context(
            patch(
                "media2text.core.runtime.monitor_startup.monitor_effectively_running",
                return_value=(False, "lock_missing"),
            )
        )
        stack.enter_context(
            patch(
                "media2text.api.services.work_queue.recover_stale_work",
                return_value={"ok": True},
            )
        )
        async with lifespan(app):
            pass
    sup.start.assert_called_once_with(cfg)


@pytest.mark.asyncio
async def test_lifespan_clears_fake_lock_and_starts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_embedded_monitor_pid",
        lambda pid: False,
    )
    app = FastAPI()
    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    sup.status_dict.return_value = {"thread_alive": False}
    sup.start.return_value = {"ok": True, "managed_by": "embedded"}
    sup.stop.return_value = {"ok": True, "stopped": True}
    with ExitStack() as stack:
        _enter_lifespan_patches(stack, supervisor=sup)
        stack.enter_context(
            patch(
                "media2text.core.runtime.monitor_startup.monitor_effectively_running",
                return_value=(False, "lock_pid_mismatch"),
            )
        )
        stack.enter_context(
            patch(
                "media2text.api.services.work_queue.recover_stale_work",
                return_value={"ok": True},
            )
        )
        async with lifespan(app):
            pass
    sup.start.assert_called_once_with(cfg)
    assert not (ws / ".monitor-watch.lock").exists()


def test_acquire_workspace_lock_writes_external_mode(tmp_path, monkeypatch) -> None:
    from media2text.core.process_lock import acquire_workspace_lock, release_workspace_lock
    from media2text.core.runtime.monitor_lock import read_lock_record

    lock = tmp_path / ".monitor-watch.lock"
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_embedded_monitor_pid",
        lambda pid: False,
    )
    fd = acquire_workspace_lock(lock)
    record = read_lock_record(lock)
    assert record is not None
    assert record.mode == "external"
    release_workspace_lock(lock, fd)


def test_acquire_workspace_lock_writes_embedded_mode_for_serve(tmp_path, monkeypatch) -> None:
    import os

    from media2text.core.process_lock import acquire_workspace_lock, release_workspace_lock
    from media2text.core.runtime.monitor_lock import read_lock_record

    lock = tmp_path / ".monitor-watch.lock"
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_embedded_monitor_pid",
        lambda pid: pid == os.getpid(),
    )
    fd = acquire_workspace_lock(lock)
    record = read_lock_record(lock)
    assert record is not None
    assert record.mode == "embedded"
    release_workspace_lock(lock, fd)
