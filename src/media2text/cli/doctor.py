import shutil
import shutil as sh
from pathlib import Path

import typer

from media2text.core.archive.health import is_index_stale, monitor_lock_pid
from media2text.core.compliance import is_compliance_accepted
from media2text.core.config import AppConfig
from media2text.core.exit_codes import EXIT_GENERAL, EXIT_OK
from media2text.core.json_out import emit
from media2text.core.platform.bilibili.auth import session_exists as bilibili_session_exists
from media2text.core.platform.douyin.auth import session_exists as douyin_session_exists
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

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
    conn = open_db(cfg)
    has_douyin = any(c.platform == "douyin" for c in CreatorRepo(conn).list_all())
    has_bilibili = any(c.platform == "bilibili" for c in CreatorRepo(conn).list_all())

    douyin_session_ok = douyin_session_exists(ws)
    bilibili_session_ok = bilibili_session_exists(ws)

    checks = [
        {"name": "ffmpeg", "ok": bool(shutil.which(cfg.live.ffmpeg_path))},
        {"name": "playwright", "ok": _playwright_ok()},
        {"name": "disk", "ok": _disk_ok(ws)},
    ]
    if has_douyin or not has_bilibili:
        checks.append(
            {
                "name": "session_douyin",
                "ok": douyin_session_ok,
                "auth_required": not douyin_session_ok,
                "relevant": has_douyin,
            }
        )
    if has_bilibili:
        checks.append(
            {
                "name": "session_bilibili",
                "ok": bilibili_session_ok,
                "auth_required": not bilibili_session_ok,
                "relevant": True,
            }
        )

    ok = all(c["ok"] for c in checks)
    if has_douyin or not has_bilibili:
        ok = ok and douyin_session_ok
    if has_bilibili:
        ok = ok and bilibili_session_ok
    emit(
        {
            "ok": ok,
            "command": "doctor",
            "checks": checks,
            "compliance_accepted": is_compliance_accepted(ws),
            "index_stale": is_index_stale(conn, ws),
            "monitor_lock_pid": monitor_lock_pid(ws),
        },
        as_json=json_out,
    )
    raise typer.Exit(EXIT_OK if ok else EXIT_GENERAL)
