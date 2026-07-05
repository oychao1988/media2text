"""MH-4b: live observe must not hold MonitorWatcher long DB connections."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.live_observe import LiveObserveService
from media2text.core.live.probe import run_live_probe_tick
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway

pytestmark = pytest.mark.desktop


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def test_monitor_watcher_has_no_long_lived_conn(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    assert not hasattr(watcher, "_conn")


def test_live_probe_tick_with_registry_uses_observe_service(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    watcher = MonitorWatcher(cfg)
    registry = MagicMock()
    registry.poll_active_for_platform = MagicMock()

    with patch.object(
        LiveObserveService,
        "poll_active_recordings",
        return_value={"active": 0},
    ) as poll_mock, patch.object(
        LiveObserveService,
        "run_finalize",
        return_value={"active": 0, "stale_cleared": 0},
    ) as fin_mock, patch.object(
        watcher._douyin_live,
        "run_probe_observe",
        return_value={"probe": True, "errors": []},
    ), patch.object(
        watcher._bilibili_live,
        "run_probe_observe",
        return_value={"probe": True, "errors": []},
    ):
        result = run_live_probe_tick(
            cfg,
            douyin=watcher._douyin_live,
            bilibili=watcher._bilibili_live,
            session_registry=registry,
        )

    assert result["active_recordings"] == 0
    poll_mock.assert_called_once()
    fin_mock.assert_called_once()
    registry.poll_active_for_platform.assert_not_called()
