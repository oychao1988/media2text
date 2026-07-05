"""Unit tests for DbWriteGateway (DL-4a)."""

from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.db import connect, with_db_lock_retry
from media2text.core.storage.write_gateway import (
    DbWriteGateway,
    WriteGuard,
    ensure_write_gateway_started,
    get_write_gateway,
    shutdown_write_gateway,
)


@pytest.fixture(autouse=True)
def _reset_gateway_singleton() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "media2text.db"
    conn = connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS gw_test (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.close()
    return db


def test_write_serializes_concurrent_updates(tmp_db: Path) -> None:
    gw = DbWriteGateway(queue_maxsize=64, write_timeout_sec=10.0, shutdown_drain_sec=2.0)
    gw.start(tmp_db)
    try:
        counter = {"n": 0}

        def bump(_conn: sqlite3.Connection) -> None:
            counter["n"] += 1
            time.sleep(0.02)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(gw.write, bump, label="bump") for _ in range(16)]
            for f in futs:
                f.result(timeout=10)

        assert counter["n"] == 16
    finally:
        gw.shutdown(timeout_sec=3.0)


def test_write_retries_on_locked(tmp_db: Path) -> None:
    gw = DbWriteGateway(
        queue_maxsize=8,
        max_lock_attempts=6,
        base_delay_sec=0.01,
        shutdown_drain_sec=2.0,
    )
    gw.start(tmp_db)
    calls = {"n": 0}

    def flaky(_conn: sqlite3.Connection) -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise sqlite3.OperationalError("database is locked")
        _conn.execute("INSERT INTO gw_test (v) VALUES ('ok')")
        _conn.commit()
        return "ok"

    try:
        assert gw.write(flaky) == "ok"
        assert calls["n"] == 2
    finally:
        gw.shutdown(timeout_sec=3.0)


def test_write_rejects_reentrant_call_from_writer_thread(tmp_db: Path) -> None:
    gw = DbWriteGateway(shutdown_drain_sec=2.0)
    gw.start(tmp_db)
    seen: list[str] = []

    def outer(conn: sqlite3.Connection) -> None:
        seen.append("outer")
        try:
            gw.write(lambda _c: seen.append("inner"))
        except RuntimeError as exc:
            seen.append(str(exc))

    try:
        gw.write(outer)
        assert seen[0] == "outer"
        assert any("writer thread" in s for s in seen)
    finally:
        gw.shutdown(timeout_sec=3.0)


def test_shutdown_drains_pending_writes(tmp_db: Path) -> None:
    gw = DbWriteGateway(shutdown_drain_sec=5.0)
    gw.start(tmp_db)
    done = threading.Event()

    def slow(_conn: sqlite3.Connection) -> None:
        time.sleep(0.05)
        done.set()

    t = threading.Thread(target=lambda: gw.write(slow, label="slow"))
    t.start()
    time.sleep(0.01)
    gw.shutdown(timeout_sec=5.0)
    t.join(timeout=2.0)
    assert done.is_set()


def test_read_uses_short_connection(tmp_db: Path) -> None:
    gw = DbWriteGateway(shutdown_drain_sec=2.0)
    gw.start(tmp_db)

    def write_one(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO gw_test (v) VALUES ('a')")
        conn.commit()

    gw.write(write_one)

    def count(conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) FROM gw_test").fetchone()
        return int(row[0])

    try:
        assert gw.read(count) == 1
    finally:
        gw.shutdown(timeout_sec=3.0)


def test_with_db_lock_retry_delegates_when_gateway_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    db = ws / "media2text.db"
    conn = connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS gw_test (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.close()

    cfg = AppConfig(workspace=ws)
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    monkeypatch.setattr(wg_mod, "_gateway", None)

    ensure_write_gateway_started(cfg)
    try:
        order: list[str] = []

        def first() -> None:
            order.append("first-start")
            time.sleep(0.05)
            order.append("first-end")

        def second() -> None:
            order.append("second")

        t1 = threading.Thread(target=lambda: with_db_lock_retry(first))
        t2 = threading.Thread(target=lambda: with_db_lock_retry(second))
        t1.start()
        time.sleep(0.01)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert order.index("first-end") < order.index("second")
    finally:
        shutdown_write_gateway()


def test_write_guard_strict_raises() -> None:
    WriteGuard.configure(strict=True)
    WriteGuard.enter()
    try:
        with pytest.raises(RuntimeError, match="blocking IO"):
            WriteGuard.assert_no_blocking_io("playwright_exclusive")
    finally:
        WriteGuard.exit()
        WriteGuard.configure(strict=False)


def test_write_guard_warning_when_not_strict() -> None:
    WriteGuard.configure(strict=False)
    WriteGuard.enter()
    try:
        WriteGuard.assert_no_blocking_io("playwright_exclusive")
    finally:
        WriteGuard.exit()
        WriteGuard.configure(strict=False)


def test_get_write_gateway_singleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    cfg = AppConfig(workspace=ws)
    monkeypatch.setattr(wg_mod, "_gateway", None)
    a = get_write_gateway(cfg)
    b = get_write_gateway(cfg)
    assert a is b


def test_doctor_write_gateway_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from media2text.core.doctor_checks import build_doctor_report
    from media2text.core.workspace import open_db

    ws = tmp_path / "data"
    ws.mkdir()
    cfg = AppConfig(workspace=ws)
    monkeypatch.setattr(wg_mod, "_gateway", None)

    conn = open_db(cfg)
    try:
        off = build_doctor_report(cfg, conn)
        assert off["write_gateway"]["running"] is False
    finally:
        conn.close()

    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    try:
        on = build_doctor_report(cfg, conn)
        assert on["write_gateway"]["running"] is True
        assert on["write_gateway"]["queue_depth"] == 0
    finally:
        conn.close()
        shutdown_write_gateway()
