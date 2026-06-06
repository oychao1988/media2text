import typer
import uvicorn

app_cli = typer.Typer(
    help=(
        "Desktop API sidecar (loopback only). "
        "Agent REST lives at /api/agent/*; /api/chat/* is a deprecated alias."
    )
)


@app_cli.callback(invoke_without_command=True)
def serve(
    port: int = typer.Option(8765, "--port", help="Listen port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (loopback only)"),
) -> None:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise typer.BadParameter("host must be loopback (127.0.0.1)")
    uvicorn.run(
        "media2text.api.app:create_app",
        factory=True,
        host=host,
        port=port,
    )
