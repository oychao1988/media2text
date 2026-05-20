import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.platform.douyin.auth import login_interactive, session_exists

app = typer.Typer(help="Authentication")


@app.command("login")
def login(
    platform: str = typer.Option("douyin", "--platform"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    if platform != "douyin":
        raise typer.BadParameter("Only douyin supported in MVP")
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    path = login_interactive(ws, headless=False)
    emit({"ok": True, "command": "auth login", "session_path": str(path)}, as_json=json_out)


@app.command("status")
def status(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    exists = session_exists(ws)
    emit(
        {
            "ok": True,
            "command": "auth status",
            "session_exists": exists,
            "auth_required": not exists,
        },
        as_json=json_out,
    )
