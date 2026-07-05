"""Write path helpers for DbWriteGateway migration (DL-4b)."""

from __future__ import annotations

from typing import Callable, TypeVar

from media2text.core.config import AppConfig

T = TypeVar("T")


class WriteAwareRepo:
    """Optional gateway routing for repo mutators."""

    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        self._conn = conn
        self._cfg = cfg

    def _mutate(self, label: str, fn: Callable[[], T]) -> T:
        from media2text.core.storage.write_gateway import WriteGuard

        if WriteGuard.is_active():
            return fn()
        if self._cfg is None:
            return fn()
        from media2text.core.storage.write_gateway import (
            ensure_write_gateway_started,
            get_write_gateway,
        )

        ensure_write_gateway_started(self._cfg)

        def _on_writer(conn) -> T:
            prev = self._conn
            self._conn = conn
            try:
                return fn()
            finally:
                self._conn = prev

        return get_write_gateway(self._cfg).write(_on_writer, label=label)
