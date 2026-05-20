import shutil
import shutil as sh
from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.exit_codes import EXIT_GENERAL, EXIT_OK
from media2text.core.json_out import emit
from media2text.core.platform.douyin.auth import session_exists

def _disk_ok(path: Path, min_gb: float = 5.0) -> bool:
    usage = sh.disk_usage(path)
    return usage.free >= min_gb * (1024**3)


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def doctor(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    session_ok = session_exists(ws)
    checks = [
        {"name": "ffmpeg", "ok": bool(shutil.which(cfg.live.ffmpeg_path))},
        {"name": "playwright", "ok": _playwright_ok()},
        {
            "name": "session",
            "ok": session_ok,
            "auth_required": not session_ok,
        },
        {"name": "disk", "ok": _disk_ok(ws)},
    ]
    ok = all(c["ok"] for c in checks if c["name"] != "session") and session_ok
    emit({"ok": ok, "command": "doctor", "checks": checks}, as_json=json_out)
    raise typer.Exit(EXIT_OK if ok else EXIT_GENERAL)
