"""Single-thread SQLite write gateway (DL-4a)."""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar, cast

import structlog

from media2text.core.storage.db import connect
from media2text.core.workspace import db_path

log = structlog.get_logger()
T = TypeVar("T")

_write_guard_local = threading.local()
_writer_thread_id: int | None = None


class WriteGuard:
    """Thread-local marker while the writer thread executes a write fn."""

    _strict: bool = False

    @classmethod
    def configure(cls, *, strict: bool) -> None:
        cls._strict = strict

    @staticmethod
    def is_active() -> bool:
        return bool(getattr(_write_guard_local, "active", False))

    @staticmethod
    def enter() -> None:
        _write_guard_local.active = True

    @staticmethod
    def exit() -> None:
        _write_guard_local.active = False

    @staticmethod
    def assert_no_blocking_io(op: str) -> None:
        if not WriteGuard.is_active():
            return
        msg = f"blocking IO ({op}) inside DbWriteGateway.write"
        if WriteGuard._strict:
            raise RuntimeError(msg)
        log.warning("write_guard_blocking_io", op=op)


@dataclass
class _WriteOp:
    fn: Callable[[sqlite3.Connection], object]
    future: Future[object]
    label: str


class DbWriteGateway:
    """Process singleton writer: one thread, one sqlite3 connection for writes."""

    def __init__(
        self,
        *,
        queue_maxsize: int = 1024,
        write_timeout_sec: float = 60.0,
        read_timeout_sec: float = 30.0,
        shutdown_drain_sec: float = 5.0,
        max_lock_attempts: int = 6,
        base_delay_sec: float = 0.2,
    ) -> None:
        self._queue_maxsize = queue_maxsize
        self._write_timeout_sec = write_timeout_sec
        self._read_timeout_sec = read_timeout_sec
        self._shutdown_drain_sec = shutdown_drain_sec
        self._max_lock_attempts = max_lock_attempts
        self._base_delay_sec = base_delay_sec
        self._queue: queue.Queue[_WriteOp | None] | None = None
        self._thread: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None
        self._db_path: Path | None = None
        self._running = False
        self._state_lock = threading.Lock()

    def is_running(self) -> bool:
        with self._state_lock:
            return self._running

    def start(self, db_path_arg: Path) -> None:
        with self._state_lock:
            if self._running:
                return
            resolved = db_path_arg.resolve()
            self._db_path = resolved
            self._queue = queue.Queue(maxsize=self._queue_maxsize)
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="db-writer",
                daemon=True,
            )
            self._running = True
            self._thread.start()
        log.info("db_write_gateway_started", db_path=str(resolved))

    def shutdown(self, *, timeout_sec: float | None = None) -> None:
        drain_sec = timeout_sec if timeout_sec is not None else self._shutdown_drain_sec
        with self._state_lock:
            if not self._running or self._queue is None:
                return
            q = self._queue
            thread = self._thread
            self._running = False
        q.put(None)
        if thread is not None:
            thread.join(timeout=drain_sec)
            if thread.is_alive():
                log.warning("db_write_gateway_shutdown_timeout", timeout_sec=drain_sec)
        with self._state_lock:
            self._queue = None
            self._thread = None
            self._conn = None
            self._db_path = None
        global _writer_thread_id
        _writer_thread_id = None
        log.info("db_write_gateway_stopped")

    def write(
        self,
        fn: Callable[[sqlite3.Connection], T],
        *,
        label: str = "",
        timeout_sec: float | None = None,
    ) -> T:
        if threading.get_ident() == _writer_thread_id:
            raise RuntimeError("DbWriteGateway.write cannot be called from writer thread")
        q = self._require_queue()
        future: Future[object] = Future()
        op = _WriteOp(fn=fn, future=future, label=label)
        try:
            q.put(op, timeout=timeout_sec or self._write_timeout_sec)
        except queue.Full as exc:
            raise TimeoutError(f"DbWriteGateway queue full (label={label!r})") from exc
        return cast(T, future.result(timeout=timeout_sec or self._write_timeout_sec))

    def read(
        self,
        fn: Callable[[sqlite3.Connection], T],
        *,
        timeout_sec: float | None = None,
    ) -> T:
        path = self._require_db_path()
        _ = timeout_sec  # reserved for future bounded read ops
        conn = connect(path)
        try:
            return fn(conn)
        finally:
            conn.close()

    def write_batch(
        self,
        fn: Callable[[sqlite3.Connection], None],
        *,
        label: str = "batch",
        timeout_sec: float | None = None,
    ) -> None:
        self.write(fn, label=label, timeout_sec=timeout_sec)

    def status(self) -> dict[str, object]:
        with self._state_lock:
            depth = self._queue.qsize() if self._queue is not None else 0
            return {
                "running": self._running,
                "queue_depth": depth,
            }

    def _require_queue(self) -> queue.Queue[_WriteOp | None]:
        with self._state_lock:
            if not self._running or self._queue is None:
                raise RuntimeError("DbWriteGateway is not running")
            return self._queue

    def _require_db_path(self) -> Path:
        with self._state_lock:
            if self._db_path is None:
                raise RuntimeError("DbWriteGateway is not running")
            return self._db_path

    def _writer_loop(self) -> None:
        global _writer_thread_id
        _writer_thread_id = threading.get_ident()
        path = self._require_db_path()
        with self._state_lock:
            q = self._queue
        if q is None:
            return
        conn = connect(path)
        with self._state_lock:
            self._conn = conn
        try:
            while True:
                item = q.get()
                if item is None:
                    break
                self._execute_write(item, conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _execute_write(self, op: _WriteOp, conn: sqlite3.Connection) -> None:
        last_exc: sqlite3.OperationalError | None = None
        for attempt in range(self._max_lock_attempts):
            WriteGuard.enter()
            try:
                result = op.fn(conn)
                op.future.set_result(result)
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    op.future.set_exception(exc)
                    return
                last_exc = exc
                if attempt + 1 >= self._max_lock_attempts:
                    op.future.set_exception(exc)
                    return
                time.sleep(self._base_delay_sec * (2**attempt))
            except Exception as exc:
                op.future.set_exception(exc)
                return
            finally:
                WriteGuard.exit()
        if last_exc is not None:
            op.future.set_exception(last_exc)


_gateway: DbWriteGateway | None = None
_gateway_lock = threading.Lock()


def get_write_gateway(cfg) -> DbWriteGateway:
    global _gateway
    with _gateway_lock:
        if _gateway is None:
            wg_cfg = cfg.monitor.write_gateway
            WriteGuard.configure(strict=cfg.monitor.write_guard_strict)
            _gateway = DbWriteGateway(
                queue_maxsize=wg_cfg.queue_maxsize,
                write_timeout_sec=wg_cfg.write_timeout_sec,
                read_timeout_sec=wg_cfg.read_timeout_sec,
                shutdown_drain_sec=wg_cfg.shutdown_drain_sec,
            )
        return _gateway


def get_write_gateway_optional() -> DbWriteGateway | None:
    with _gateway_lock:
        return _gateway


def ensure_write_gateway_started(cfg) -> DbWriteGateway:
    gw = get_write_gateway(cfg)
    if not gw.is_running():
        gw.start(db_path(cfg.ensure_workspace()))
    return gw


def shutdown_write_gateway(*, timeout_sec: float | None = None) -> None:
    global _gateway
    with _gateway_lock:
        if _gateway is None:
            return
        gw = _gateway
        _gateway = None
    if gw.is_running():
        gw.shutdown(timeout_sec=timeout_sec)


def write_gateway_status(cfg) -> dict[str, object]:
    gw = get_write_gateway_optional()
    if gw is None or not gw.is_running():
        return {"running": False, "queue_depth": 0}
    return gw.status()
