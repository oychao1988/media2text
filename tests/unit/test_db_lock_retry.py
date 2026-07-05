import sqlite3

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.db import with_db_lock_retry
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def test_with_db_lock_retry_inline_without_gateway() -> None:
    calls = {"n": 0}

    def bump() -> None:
        calls["n"] += 1

    with_db_lock_retry(bump)
    assert calls["n"] == 1


def test_with_db_lock_retry_delegates_when_gateway_running(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    cfg = AppConfig(workspace=ws)
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    calls = {"n": 0}

    def bump() -> None:
        calls["n"] += 1

    with_db_lock_retry(bump)
    assert calls["n"] == 1


def test_with_db_lock_retry_reraises_non_lock_errors(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    cfg = AppConfig(workspace=ws)
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)

    def bad() -> None:
        raise sqlite3.OperationalError("no such table: foo")

    try:
        with_db_lock_retry(bad)
    except sqlite3.OperationalError as exc:
        assert "no such table" in str(exc)
    else:
        raise AssertionError("expected OperationalError")
