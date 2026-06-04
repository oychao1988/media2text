"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends

from media2text.core.config import AppConfig
from media2text.core.workspace import open_db

_spawn_login_impl: Callable[[str], dict] | None = None


def get_cfg() -> AppConfig:
    return AppConfig.load()


def get_db(
    cfg: Annotated[AppConfig, Depends(get_cfg)],
) -> Generator:
    conn = open_db(cfg)
    try:
        yield conn
    finally:
        conn.close()


def set_spawn_login(impl: Callable[[str], dict] | None) -> None:
    global _spawn_login_impl
    _spawn_login_impl = impl


def spawn_auth_login(platform: str) -> dict:
    if _spawn_login_impl is not None:
        return _spawn_login_impl(platform)
    import subprocess
    import sys

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "media2text",
            "auth",
            "login",
            "--platform",
            platform,
        ],
        start_new_session=True,
    )
    return {"ok": True, "spawned": True, "platform": platform}
