import os
import sys

import typer
import uvicorn

from media2text.core.config import AppConfig
from media2text.core.process_lock import LockError, acquire_workspace_lock, release_workspace_lock

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

    if os.environ.get("M2T_DESKTOP_MANAGED") != "1":
        print(
            "[serve] 建议通过桌面端启动，手动 serve 可能与其他实例冲突",
            file=sys.stderr,
        )

    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    lock_path = ws / ".serve.lock"
    try:
        lock_fd = acquire_workspace_lock(lock_path)
    except LockError:
        pid = None
        try:
            pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        msg = "[serve] serve 已在运行"
        if pid is not None:
            msg += f" (PID {pid})"
        print(msg, file=sys.stderr)
        raise typer.Exit(code=1)

    try:
        uvicorn.run(
            "media2text.api.app:create_app",
            factory=True,
            host=host,
            port=port,
        )
    finally:
        release_workspace_lock(lock_path, lock_fd)
