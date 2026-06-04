import typer

from media2text.core.config import AppConfig
from media2text.core.doctor_checks import build_doctor_report
from media2text.core.exit_codes import EXIT_GENERAL, EXIT_OK
from media2text.core.json_out import emit
from media2text.core.workspace import open_db


def doctor(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    report = build_doctor_report(cfg, conn)
    emit({"command": "doctor", **report}, as_json=json_out)
    raise typer.Exit(EXIT_OK if report["ok"] else EXIT_GENERAL)
