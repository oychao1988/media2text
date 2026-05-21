import typer

from media2text import __version__
from media2text.cli import archive as archive_cli
from media2text.cli import auth as auth_cli
from media2text.cli import creator as creator_cli
from media2text.cli import download as download_cli
from media2text.cli import monitor as monitor_cli
from media2text.cli import notify as notify_cli
from media2text.cli import pipeline as pipeline_cli
from media2text.cli import transcribe as transcribe_cli
from media2text.cli.doctor import doctor
from media2text.core.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="Douyin media capture and transcribe CLI")
app.add_typer(archive_cli.app, name="archive")
app.add_typer(auth_cli.app, name="auth")
app.add_typer(creator_cli.app, name="creator")
app.add_typer(download_cli.app, name="download")
app.add_typer(monitor_cli.app, name="monitor")
app.add_typer(transcribe_cli.app, name="transcribe")
app.add_typer(pipeline_cli.app, name="pipeline")
app.add_typer(notify_cli.app, name="notify")
app.command("doctor")(doctor)


@app.callback()
def main() -> None:
    configure_logging()


@app.command()
def version() -> None:
    typer.echo(__version__)
