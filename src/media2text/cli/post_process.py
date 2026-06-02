import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.live.post_process import drain_pending_jobs
from media2text.core.notify import NotifyService
from media2text.core.workspace import open_db

app = typer.Typer(help="Live recording post-process queue (transcribe / summarize / cloud)")


@app.command("run")
def run_cmd(
    limit: int = typer.Option(10, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    notify = NotifyService(cfg)
    results = drain_pending_jobs(cfg, conn, notify=notify, limit=limit)
    emit(
        {
            "ok": True,
            "command": "post-process run",
            "processed": len(results),
            "results": results,
        },
        as_json=json_out,
    )
