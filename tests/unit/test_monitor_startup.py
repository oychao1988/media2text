import json
from unittest.mock import MagicMock, patch


from media2text.core.config import AppConfig, DesktopConfig
from media2text.core.runtime.monitor_startup import (
    assert_monitor_slot_available,
    auto_start_embedded_monitor,
    monitor_owner_status,
    prepare_embedded_monitor_startup,
)


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True),
    )


def test_monitor_owner_status_none(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    assert monitor_owner_status(cfg) == {
        "running": False,
        "managed_by": "none",
        "pid": None,
    }


def test_monitor_owner_status_external(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 424242
    (ws / ".monitor-watch.lock").write_text(
        json.dumps({"pid": external_pid, "mode": "external"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_embedded_monitor_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.clear_invalid_monitor_lock",
        lambda _path: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.read_lock_pid",
        lambda _path: external_pid,
    )
    assert monitor_owner_status(cfg) == {
        "running": True,
        "managed_by": "external",
        "pid": external_pid,
    }


def test_assert_monitor_slot_available_blocks_external(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    external_pid = 515151
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_embedded_monitor_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.clear_invalid_monitor_lock",
        lambda _path: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.read_lock_pid",
        lambda _path: external_pid,
    )
    blocked = assert_monitor_slot_available(cfg)
    assert blocked is not None
    assert blocked["already_running"] is True
    assert blocked["managed_by"] == "external"


def test_auto_start_skips_external(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    external_pid = 616161
    (ws / ".monitor-watch.lock").write_text(
        json.dumps({"pid": external_pid, "mode": "external"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_monitor_watch_pid",
        lambda pid: pid == external_pid,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.is_embedded_monitor_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.clear_invalid_monitor_lock",
        lambda _path: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.read_lock_pid",
        lambda _path: external_pid,
    )
    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    result = auto_start_embedded_monitor(cfg, sup, recover_stale=False)
    assert result["skipped"] is True
    assert result["managed_by"] == "external"
    sup.start.assert_not_called()
    sup.takeover.assert_not_called()


def test_auto_start_starts_when_no_owner(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    sup = MagicMock()
    sup._is_embedded_running.return_value = False
    sup.start.return_value = {"ok": True, "managed_by": "embedded"}
    with patch(
        "media2text.api.services.work_queue.recover_stale_work",
        return_value={"ok": True},
    ) as recover:
        result = auto_start_embedded_monitor(cfg, sup)
    assert result["ok"] is True
    sup.start.assert_called_once_with(cfg)
    recover.assert_called_once()


def test_prepare_restarts_stuck_embedded_thread(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    sup = MagicMock()
    sup._is_embedded_running.return_value = True
    sup.status_dict.return_value = {"thread_alive": True, "managed_by": "embedded"}
    sup.takeover.return_value = {"ok": True, "start": {"ok": True, "managed_by": "embedded"}}
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_startup.monitor_effectively_running",
        lambda *_args, **_kwargs: (False, "heartbeat_stale"),
    )
    with patch(
        "media2text.api.services.work_queue.recover_stale_work",
        return_value={"ok": True},
    ):
        result = prepare_embedded_monitor_startup(cfg, sup)
    assert result["ok"] is True
    sup.takeover.assert_called_once_with(cfg)
    sup.start.assert_not_called()
