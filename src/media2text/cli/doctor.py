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
from media2text.core.cloud.aliyundrive import load_token
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

def _disk_ok(path: Path, min_gb: float = 5.0) -> bool:
    usage = sh.disk_usage(path)
    return usage.free >= min_gb * (1024**3)


def _playwright_import_ok() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _playwright_browser_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return bool(exe and Path(exe).exists())
    except Exception:
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
        {
            "name": "playwright",
            "ok": _playwright_import_ok(),
            "hint": "pip install playwright（bundled slim 版需自行安装）",
        },
        {
            "name": "playwright_browser",
            "ok": _playwright_browser_ok(),
            "hint": "playwright install chromium",
        },
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

    ad = cfg.aliyundrive
    if ad.enabled:
        token_path = cfg.aliyundrive_token_path()
        aliyundrive_ok = False
        if token_path.is_file():
            try:
                aliyundrive_ok = bool(load_token(token_path).get("refresh_token"))
            except (OSError, ValueError):
                aliyundrive_ok = False
        checks.append(
            {
                "name": "session_aliyundrive",
                "ok": aliyundrive_ok,
                "auth_required": not aliyundrive_ok,
                "relevant": True,
                "hint": "media2text auth login --platform aliyundrive",
            }
        )

    ok = all(c["ok"] for c in checks if c["name"] not in ("playwright", "playwright_browser"))
    if has_douyin or not has_bilibili:
        ok = ok and douyin_session_ok
    if has_bilibili:
        ok = ok and bilibili_session_ok
    if ad.enabled:
        ok = ok and any(
            c["ok"] for c in checks if c["name"] == "session_aliyundrive"
        )
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
