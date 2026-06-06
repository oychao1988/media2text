"""Desktop FastAPI sidecar."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from media2text.api.app import FastAPI as _FastAPI

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from media2text.api.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

