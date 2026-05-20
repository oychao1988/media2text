import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.platform.douyin.live import LiveWatcher

app = typer.Typer(help="Live stream monitoring")


@app.command("watch")
def watch(
    daemon: bool = typer.Option(False, "--daemon"),
    creator_id: str | None = typer.Option(None, "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    watcher = LiveWatcher(cfg)
    if daemon:
        watcher.run_daemon(creator_id=creator_id)
        return
    result = watcher.run_once(creator_id=creator_id)
    emit({"ok": True, "command": "live watch", **result}, as_json=json_out)
