"""StateWriter routes mutations through DbWriteGateway when cfg is set (DL-4b)."""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def test_write_obs_uses_gateway(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    writer = StateWriter(conn, cfg=cfg)
    calls: list[str] = []

    original = writer._mutate

    def track(label: str, fn):
        calls.append(label)
        return original(label, fn)

    monkeypatch.setattr(writer, "_mutate", track)
    writer.write_obs("sess-1", ffmpeg_alive=True, stt_alive=None, still_live=True)
    assert calls == ["state.write_obs"]


def test_set_offline_since_begin_immediate_on_writer_conn(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    cid = __import__(
        "media2text.core.storage.repos", fromlist=["CreatorRepo"]
    ).CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAoffline",
        profile_url="https://example.com",
        monitor_enabled=True,
    )
    sid = __import__(
        "media2text.core.storage.repos", fromlist=["LiveSessionRepo"]
    ).LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/tmp/x.flv",
    )
    writer = StateWriter(conn, cfg=cfg)
    with patch.object(writer._notify, "emit") as emit:
        writer.set_offline_since(sid, "2026-07-05T12:00:00+00:00", creator_id=cid)
    row = conn.execute(
        "SELECT offline_since_at FROM live_sessions WHERE id = ?", (sid,)
    ).fetchone()
    assert row[0] is not None
    emit.assert_called_once()


def test_scheduler_write_batch_single_commit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from media2text.core.live.task_scheduler import TaskSchedulerLoop

    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    gw = wg_mod.get_write_gateway(cfg)
    batch_calls: list[str] = []

    def capture_batch(fn, *, label: str = "batch", timeout_sec=None):
        batch_calls.append(label)
        conn = open_db(cfg)
        try:
            fn(conn)
        finally:
            conn.close()

    monkeypatch.setattr(gw, "write_batch", capture_batch)
    loop = TaskSchedulerLoop(
        cfg,
        watcher=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        live_pool=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        content_pool=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        post_pool=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        heavy_pool=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        stop=threading.Event(),
    )
    loop.tick_once(open_db(cfg))
    assert batch_calls == []

    gw.write_batch(lambda conn: loop.tick_once(conn), label="scheduler_tick")
    assert batch_calls == ["scheduler_tick"]
