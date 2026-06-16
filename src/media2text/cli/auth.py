import os
from pathlib import Path

import typer

from media2text.core.cloud.aliyundrive import load_token
from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.platform.bilibili.auth import (
    login_interactive as bilibili_login,
    session_path as bilibili_session_path,
)
from media2text.core.platform.douyin.auth import (
    login_interactive as douyin_login,
    session_path as douyin_session_path,
)

app = typer.Typer(help="Authentication")


def _normalize_platform(platform: str) -> str:
    key = platform.strip().lower()
    if key not in ("douyin", "bilibili", "aliyundrive"):
        raise typer.BadParameter("platform must be douyin, bilibili, or aliyundrive")
    return key


def _aliyundrive_clear_session(cfg: AppConfig) -> None:
    ws = cfg.ensure_workspace()
    for name in ("aliyundrive.token.json", "aliyundrive.json"):
        path = ws / "sessions" / name
        path.unlink(missing_ok=True)
    profile = ws / ".playwright" / "aliyundrive-profile"
    if profile.is_dir():
        import shutil

        shutil.rmtree(profile)


def _aliyundrive_login(cfg: AppConfig, *, force: bool = False) -> Path:
    import sys
    from pathlib import Path as P

    root = P(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.aliyundrive_login import login_with_profile

    ws = cfg.ensure_workspace()
    if force:
        _aliyundrive_clear_session(cfg)
    mode = os.environ.get("ALIYUN_DRIVE_LOGIN_MODE", "auto").strip().lower() or "auto"
    phone = os.environ.get("ALIYUN_DRIVE_PHONE", "").strip()
    password = os.environ.get("ALIYUN_DRIVE_PASSWORD", "").strip()
    if mode == "auto" and phone and password:
        mode = "password"
    use_chrome = mode == "password" or os.environ.get(
        "ALIYUN_DRIVE_USE_CHROME", ""
    ).strip().lower() in ("1", "true", "yes")
    return login_with_profile(
        workspace=ws,
        headless=False,
        mode=mode,
        use_chrome=use_chrome,
        phone=phone or None,
        password=password or None,
    )


def _aliyundrive_token_exists(cfg: AppConfig) -> bool:
    path = cfg.aliyundrive_token_path()
    if not path.is_file():
        return False
    try:
        token = load_token(path)
    except (OSError, ValueError):
        return False
    return bool(token.get("refresh_token"))


@app.command("login")
def login(
    platform: str = typer.Option("douyin", "--platform"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Aliyun Drive: clear saved browser profile and token before login",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    key = _normalize_platform(platform)
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    if key == "aliyundrive":
        path = _aliyundrive_login(cfg, force=force)
    elif key == "bilibili":
        path = bilibili_login(ws, headless=False)
    else:
        path = douyin_login(ws, headless=False)
    emit(
        {
            "ok": True,
            "command": "auth login",
            "platform": key,
            "session_path": str(path),
        },
        as_json=json_out,
    )


@app.command("status")
def status(
    platform: str = typer.Option("douyin", "--platform"),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Probe saved session online (Douyin opens headless browser)",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    key = _normalize_platform(platform)
    cfg = AppConfig.load()
    from media2text.core.platform.session_validate import platform_auth_snapshot

    snap = platform_auth_snapshot(cfg, key, validate=validate, refresh=True)
    payload = snap.as_dict()
    ws = cfg.ensure_workspace()
    if key == "aliyundrive":
        session = cfg.aliyundrive_token_path()
    elif key == "bilibili":
        session = bilibili_session_path(ws)
    else:
        session = douyin_session_path(ws)
    emit(
        {
            "ok": True,
            "command": "auth status",
            "platform": key,
            "session_exists": payload["configured"],
            "session_path": str(session),
            **payload,
        },
        as_json=json_out,
    )
