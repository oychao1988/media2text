import time
from unittest.mock import MagicMock, patch

import pytest

from media2text.api.services import monitor_self_heal as msh
from media2text.api.services.monitor_self_heal import maybe_self_heal_monitor
from media2text.core.config import AppConfig, DesktopConfig

pytestmark = pytest.mark.desktop


def test_maybe_self_heal_takeover_when_stopped(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=True),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "lock_pid_mismatch"),
    ):
        with patch.object(sup, "takeover", return_value={"ok": True, "start": {"ok": True}}) as takeover:
            result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["healed"] is True
    takeover.assert_called_once()


def test_maybe_self_heal_hourly_rate_limit(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = 0.0
    msh._heal_timestamps.clear()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(
            auto_start_monitor=True,
            monitor_self_heal=True,
            monitor_self_heal_max_per_hour=3,
            monitor_self_heal_cooldown_sec=0,
        ),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    now = time.monotonic()
    msh._heal_timestamps.extend([now - 10, now - 20, now - 30])
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "heartbeat_stale"),
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["healed"] is False
    assert result["skipped"] == "hourly_limit"


def test_maybe_self_heal_skips_when_external_just_started(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = 0.0
    msh._heal_timestamps.clear()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=True),
    )
    cfg.ensure_workspace()
    lock = cfg.ensure_workspace() / ".monitor-watch.lock"
    lock.write_text("4242", encoding="utf-8")
    sup = MagicMock()

    def _alive(pid: int) -> bool:
        return pid == 4242

    monkeypatch.setattr("media2text.core.runtime.monitor_lock._pid_alive", _alive)
    with (
        patch("media2text.api.services.monitor_self_heal.clear_invalid_monitor_lock"),
        patch(
            "media2text.api.services.monitor_self_heal.is_monitor_watch_pid",
            return_value=True,
        ),
        patch(
            "media2text.api.services.monitor_self_heal.read_lock_pid",
            return_value=4242,
        ),
        patch(
            "media2text.api.services.monitor_self_heal.monitor_effectively_running",
            return_value=(False, "lock_missing"),
        ),
        patch.object(sup, "takeover") as takeover,
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["skipped"] == "external_started"
    takeover.assert_not_called()


def test_maybe_self_heal_repairs_embedded_lock(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = 0.0
    msh._heal_timestamps.clear()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=True),
    )
    cfg.ensure_workspace()
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "embedded", "thread_alive": True}
    sup.repair_embedded_lock.return_value = {
        "ok": True,
        "action": "repair_embedded_lock",
        "pid": 12345,
    }
    running_checks = iter([(False, "embedded_thread_dead"), (True, None)])

    def _effectively_running(*_args, **_kwargs):
        return next(running_checks)

    with (
        patch(
            "media2text.api.services.monitor_self_heal.monitor_effectively_running",
            side_effect=_effectively_running,
        ),
        patch.object(sup, "takeover") as takeover,
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["healed"] is True
    assert result["repair"]["action"] == "repair_embedded_lock"
    sup.repair_embedded_lock.assert_called_once_with(cfg)
    takeover.assert_not_called()


def test_maybe_self_heal_cooldown(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = time.monotonic()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(
            auto_start_monitor=True,
            monitor_self_heal=True,
            monitor_self_heal_cooldown_sec=120,
        ),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "heartbeat_stale"),
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=False)
    assert result["healed"] is False
    assert result["skipped"] == "cooldown"
