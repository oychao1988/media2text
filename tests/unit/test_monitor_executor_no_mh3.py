"""MH-4c: worker dispatch uses SessionStateMachineRegistry, not _core_for_task."""

from __future__ import annotations

import inspect

import pytest

from media2text.core.config import AppConfig
from media2text.core.live import monitor_executor as me
from media2text.core.monitor.watcher import MonitorWatcher

pytestmark = pytest.mark.desktop


def test_core_for_task_removed() -> None:
    assert "_core_for_task" not in dir(me)


def test_monitor_watcher_has_no_conn_attribute(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    assert not hasattr(watcher, "_conn")


def test_require_registry_delegates_to_watcher(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    registry = watcher.ensure_session_registry()
    assert registry is watcher.session_registry


def test_live_dispatch_functions_use_registry(monkeypatch) -> None:
    sources = [
        inspect.getsource(me._run_finalize),
        inspect.getsource(me._run_prepare_live_recording),
        inspect.getsource(me._run_reconnect_recording),
        inspect.getsource(me._run_start_streaming_stt),
        inspect.getsource(me._run_reconnect_streaming_stt),
    ]
    for src in sources:
        assert "_require_registry" in src
        assert "core_for_platform" not in src
