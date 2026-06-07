"""Write-origin tracking for skill_manage (M7b)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

FOREGROUND = "foreground"
BACKGROUND_REVIEW = "background_review"

_write_origin: ContextVar[str] = ContextVar("skill_write_origin", default=FOREGROUND)


def get_current_write_origin() -> str:
    return _write_origin.get()


@contextmanager
def write_origin_ctx(origin: str) -> Iterator[None]:
    token = _write_origin.set(origin)
    try:
        yield
    finally:
        _write_origin.reset(token)
