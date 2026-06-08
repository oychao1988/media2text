from __future__ import annotations

import subprocess
import threading
from contextlib import contextmanager
from typing import Iterator

import structlog

log = structlog.get_logger()

_probe_ctx = threading.local()


class ProbeViolationError(RuntimeError):
    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(f"probe execution guard violations: {violations}")


class ProbeExecutionGuard:
    @staticmethod
    def enter_probe_tick() -> None:
        _probe_ctx.active = True
        _probe_ctx.violations = []

    @staticmethod
    def exit_probe_tick(*, strict: bool = False) -> None:
        violations = list(getattr(_probe_ctx, "violations", []))
        _probe_ctx.active = False
        if hasattr(_probe_ctx, "violations"):
            del _probe_ctx.violations
        if violations and strict:
            raise ProbeViolationError(violations)
        if violations:
            log.error("probe_guard_violation", violations=violations)

    @staticmethod
    def record_violation(name: str) -> None:
        if getattr(_probe_ctx, "active", False):
            _probe_ctx.violations.append(name)

    @staticmethod
    def is_active() -> bool:
        return bool(getattr(_probe_ctx, "active", False))

    @staticmethod
    @contextmanager
    def probe_tick(*, strict: bool = False) -> Iterator[None]:
        ProbeExecutionGuard.enter_probe_tick()
        try:
            yield
        finally:
            ProbeExecutionGuard.exit_probe_tick(strict=strict)


def guarded_popen(*args, **kwargs) -> subprocess.Popen:
    ProbeExecutionGuard.record_violation("Popen")
    return subprocess.Popen(*args, **kwargs)
