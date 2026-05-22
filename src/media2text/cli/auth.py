import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.platform.bilibili.auth import (
    login_interactive as bilibili_login,
    session_exists as bilibili_session_exists,
    session_path as bilibili_session_path,
)
from media2text.core.platform.douyin.auth import (
    login_interactive as douyin_login,
    session_exists as douyin_session_exists,
    session_path as douyin_session_path,
)

app = typer.Typer(help="Authentication")


def _normalize_platform(platform: str) -> str:
    key = platform.strip().lower()
    if key not in ("douyin", "bilibili"):
        raise typer.BadParameter("platform must be douyin or bilibili")
    return key


@app.command("login")
def login(
    platform: str = typer.Option("douyin", "--platform"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    key = _normalize_platform(platform)
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    if key == "bilibili":
        path = bilibili_login(ws, headless=False)
    else:
        path = douyin_login(ws, headless=False)
    emit(
        {
            "ok": True,
            "command": "auth login",
            "platform": key,
            "session_path": str(path),
        },
        as_json=json_out,
    )


@app.command("status")
def status(
    platform: str = typer.Option("douyin", "--platform"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    key = _normalize_platform(platform)
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    if key == "bilibili":
        exists = bilibili_session_exists(ws)
        session = bilibili_session_path(ws)
    else:
        exists = douyin_session_exists(ws)
        session = douyin_session_path(ws)
    emit(
        {
            "ok": True,
            "command": "auth status",
            "platform": key,
            "session_exists": exists,
            "session_path": str(session),
            "auth_required": not exists,
        },
        as_json=json_out,
    )
