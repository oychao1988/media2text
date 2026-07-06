import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.monitor.errors import ReconcilerDisabledError
from media2text.core.process_lock import LockError

app = typer.Typer(help="Unified creator monitoring (live + VOD)")


@app.command("watch")
def watch(
    daemon: bool = typer.Option(
        False,
        "--daemon",
        help="Run continuously (recommended). Without --daemon: one LiveTick + "
        "SchedulerTick round (same paths as daemon; no SlowTick).",
    ),
    creator_id: str | None = typer.Option(None, "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    watcher = MonitorWatcher(cfg)
    if daemon:
        try:
            watcher.run_daemon(creator_id=creator_id)
        except ReconcilerDisabledError as exc:
            emit(
                {
                    "ok": False,
                    "command": "monitor watch",
                    "error": str(exc),
                    "reconciler_enabled": False,
                },
                as_json=json_out,
            )
            raise typer.Exit(1) from None
        except LockError as exc:
            from media2text.core.runtime.monitor_startup import assert_monitor_slot_available

            blocked = assert_monitor_slot_available(cfg) or {}
            emit(
                {
                    "ok": False,
                    "command": "monitor watch",
                    "already_running": True,
                    "managed_by": blocked.get("managed_by"),
                    "pid": blocked.get("pid"),
                    "error": str(exc),
                },
                as_json=json_out,
            )
            raise typer.Exit(1) from None
        return
    result = watcher.run_once(creator_id=creator_id)
    emit({"ok": True, "command": "monitor watch", **result}, as_json=json_out)
