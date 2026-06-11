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

    cfg = AppConfig.load()
    log_dir = cfg.ensure_workspace() / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"auth-login-{platform.strip().lower()}.log"
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n--- spawn auth login {platform} ---\n")
    log_file.flush()

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
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    return {
        "ok": True,
        "spawned": True,
        "platform": platform,
        "log_path": str(log_path),
    }
