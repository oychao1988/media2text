import typer

from media2text.core.compliance import accept_compliance
from media2text.core.config import AppConfig
from media2text.core.exit_codes import EXIT_OK
from media2text.core.json_out import emit

app = typer.Typer(help="Compliance disclaimer acceptance")


@app.command("accept")
def accept_cmd(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    record = accept_compliance(cfg.ensure_workspace())
    emit(
        {
            "ok": True,
            "command": "compliance accept",
            "accepted_at": record.accepted_at,
            "version": record.version,
        },
        as_json=json_out,
    )
    raise typer.Exit(EXIT_OK)
