import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.pipeline.runner import run_pipeline

app = typer.Typer(help="End-to-end pipeline")


@app.command("run")
def run(
    creator_id: str = typer.Option(..., "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    result = run_pipeline(cfg, creator_id=creator_id)
    emit(result, as_json=json_out)
    from media2text.core.cli_exit import raise_for_result

    raise_for_result(result)
