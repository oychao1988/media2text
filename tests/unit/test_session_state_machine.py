from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.session_state import (
    SessionHandle,
    SessionStateMachine,
    SessionStateMachineRegistry,
)
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import NotifyService
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def _registry(tmp_path, monkeypatch) -> SessionStateMachineRegistry:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    watcher = MagicMock()
    watcher._cfg = cfg
    watcher._session_runtime = SessionRuntime()
    watcher._notify = NotifyService(cfg)
    watcher.core_for_platform = MagicMock()
    return SessionStateMachineRegistry(
        cfg,
        runtime=watcher._session_runtime,
        gateway=wg_mod.get_write_gateway(cfg),
        watcher=watcher,
        notify=watcher._notify,
    )


def test_mark_offline_pending_sets_offline_since(tmp_path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    conn = open_db(registry._cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsm",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=registry._cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=4242,
    )
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    machine = registry.get_or_create(row, platform="douyin")
    machine.mark_offline_pending("2026-07-05T12:00:00+00:00")
    updated = LiveSessionRepo(conn).get(sid)
    assert updated is not None
    assert updated.offline_since_at is not None


def test_transition_to_finalizing_sets_remuxing(tmp_path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    conn = open_db(registry._cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAfin",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=registry._cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=4242,
    )
    handle = SessionHandle(session_id=sid, creator_id=cid, platform="douyin")
    machine = SessionStateMachine(
        registry._cfg,
        handle,
        runtime=registry._runtime,
        gateway=registry._gateway,
        watcher=registry._watcher,
        notify=registry._notify,
    )
    machine.transition_to_finalizing()
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.status == "remuxing"
