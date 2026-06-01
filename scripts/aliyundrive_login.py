#!/usr/bin/env python3
"""Playwright + persistent profile login for personal Aliyun Drive (alipan.com).

Why password login often fails:
  Alibaba slider captcha (NoCaptcha) flags Playwright's bundled Chromium.
  Manual drag in that window may still fail. Prefer QR / desktop quick-login,
  installed Chrome (`--channel chrome`), or import refresh_token from real browser.

Modes (--mode):
  qr       Scan with Aliyun Drive App (recommended, no slider)
  desktop  Click desktop-client avatar in oauth iframe (if installed)
  password Phone + password (needs --channel chrome; slider may still block)
  token    Import ALIYUN_DRIVE_REFRESH_TOKEN from .env (no browser)

Usage:
  source .venv/bin/activate
  set -a && source .env && set +a

  python scripts/aliyundrive_login.py                    # auto mode
  python scripts/aliyundrive_login.py --mode qr
  python scripts/aliyundrive_login.py --mode token
  python scripts/aliyundrive_login.py --mode password --channel chrome
  python scripts/aliyundrive_login.py --probe

.env keys:
  ALIYUN_DRIVE_LOGIN_MODE=qr|desktop|password|token|auto
  ALIYUN_DRIVE_PHONE / ALIYUN_DRIVE_PASSWORD   (password mode)
  ALIYUN_DRIVE_REFRESH_TOKEN                   (token mode)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Frame, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT / "data"
SIGN_IN_URL = "https://www.alipan.com/sign/in"
DRIVE_URL_PREFIX = "https://www.alipan.com/drive"
MODES = ("auto", "qr", "desktop", "password", "token")


def _oauth_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        if "oauth/authorize" in frame.url:
            return frame
    return None


def _passport_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        if "passport" in frame.url and "mini_login" in frame.url:
            return frame
    return None


def _has_desktop_quick_login(page: Page) -> bool:
    oauth = _oauth_frame(page)
    return oauth is not None and oauth.locator(".desktop-login").count() > 0


def _try_desktop_quick_login(oauth: Frame) -> bool:
    if oauth.locator(".desktop-login").count() == 0:
        return False
    result = oauth.evaluate(
        """
        () => {
          const desktop = document.querySelector('.desktop-login');
          if (!desktop) return 'missing';
          const avatar = desktop.querySelector('img, [class*="avatar"]');
          if (avatar) { avatar.click(); return 'avatar'; }
          desktop.click();
          return 'desktop';
        }
        """
    )
    return result in ("avatar", "desktop")


def _switch_passport_to_account_login(passport: Frame) -> None:
    passport.evaluate("() => document.querySelector('a.sms-login-link')?.click()")
    passport.wait_for_timeout(800)
    passport.locator("#fm-login-id").wait_for(state="visible", timeout=15_000)


def _ensure_qr_tab(passport: Frame) -> None:
    """Stay on default QR tab (do not click 账号登录)."""
    qr_title = passport.locator(".sms-login-title, label.sms-login-title")
    if qr_title.count() > 0:
        qr_title.first.click(force=True)
        passport.wait_for_timeout(500)


def _maybe_fill_credentials(frame: Frame, phone: str, password: str) -> bool:
    if not phone or not password:
        return False
    frame.locator("#fm-login-id").fill(phone)
    frame.locator("#fm-login-password").fill(password)
    frame.get_by_role("button", name="登录").click()
    return True


def _read_token(page: Page) -> dict | None:
    raw = page.evaluate(
        """
        () => {
          for (const k of ['token', 'pds_token', 'auth_token']) {
            const v = localStorage.getItem(k) || sessionStorage.getItem(k);
            if (v) return { key: k, value: v };
          }
          return null;
        }
        """
    )
    if not raw:
        return None
    try:
        token_obj = json.loads(raw["value"])
    except json.JSONDecodeError:
        return {"raw_key": raw["key"], "raw_value": raw["value"]}
    if isinstance(token_obj, dict):
        token_obj["_storage_key"] = raw["key"]
    return token_obj


def _wait_for_drive(page: Page, *, timeout_sec: float = 300.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if page.url.startswith(DRIVE_URL_PREFIX):
            return
        page.wait_for_timeout(1000)
    raise TimeoutError(f"Timed out waiting for drive redirect; last url={page.url}")


def _resolve_mode(requested: str, *, has_credentials: bool, has_token: bool) -> str:
    mode = requested.strip().lower() or "auto"
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode != "auto":
        return mode
    if has_token:
        return "token"
    # Password + Playwright Chromium almost always hits unc passable slider → prefer QR.
    return "qr"


def _launch_kwargs(*, headless: bool, use_chrome: bool) -> dict:
    kwargs: dict = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "locale": "zh-CN",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if use_chrome:
        kwargs["channel"] = "chrome"
    return kwargs


def _save_token_dict(token: dict, workspace: Path) -> Path:
    session_dir = workspace / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    token_path = session_dir / "aliyundrive.token.json"
    token_path.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    token_path.chmod(0o600)
    print(f"[aliyundrive] refresh_token saved: {token_path}")
    return token_path


def _save_session(context: BrowserContext, page: Page, workspace: Path) -> Path:
    session_dir = workspace / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    storage_path = session_dir / "aliyundrive.json"

    token = _read_token(page)
    if not token or not token.get("refresh_token"):
        raise RuntimeError(
            "Logged in but refresh_token not found in localStorage/sessionStorage"
        )

    context.storage_state(path=str(storage_path))
    _save_token_dict(token, workspace)
    storage_path.chmod(0o600)
    print(f"[aliyundrive] storage_state: {storage_path}")
    return storage_path


def import_refresh_token(*, workspace: Path = DEFAULT_WORKSPACE, refresh_token: str = "") -> Path:
    refresh_token = refresh_token or os.environ.get("ALIYUN_DRIVE_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        raise RuntimeError(
            "Set ALIYUN_DRIVE_REFRESH_TOKEN in .env, or paste token from real browser:\n"
            "  1) Login at https://www.alipan.com in Chrome/Safari\n"
            "  2) DevTools Console: JSON.parse(localStorage.token).refresh_token\n"
            "  3) python scripts/aliyundrive_login.py --mode token"
        )
    token = {"refresh_token": refresh_token, "_source": "env_import"}
    _save_token_dict(token, workspace)
    return workspace / "sessions" / "aliyundrive.token.json"


def _prompt_for_mode(page: Page, mode: str) -> None:
    if mode == "qr":
        print(
            "[aliyundrive] QR login: open Aliyun Drive App → Scan → confirm on phone.\n"
            "  (No slider captcha on this path.)"
        )
    elif mode == "desktop":
        print(
            "[aliyundrive] Desktop quick-login: click your avatar in the browser window.\n"
            "  If that fails, click 「切换为其他方式登录」 then use QR tab."
        )
    elif mode == "password":
        print(
            "[aliyundrive] Password login: slider captcha may fail in automation browsers.\n"
            "  If blocked, Ctrl+C and retry with: --mode qr  or  --mode token"
        )


def login_with_profile(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    headless: bool = False,
    mode: str = "auto",
    use_chrome: bool = False,
    phone: str | None = None,
    password: str | None = None,
) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    profile_dir = workspace / ".playwright" / "aliyundrive-profile"
    phone = phone or os.environ.get("ALIYUN_DRIVE_PHONE", "").strip()
    password = password or os.environ.get("ALIYUN_DRIVE_PASSWORD", "").strip()
    refresh_token = os.environ.get("ALIYUN_DRIVE_REFRESH_TOKEN", "").strip()

    mode = _resolve_mode(mode, has_credentials=bool(phone and password), has_token=bool(refresh_token))
    if mode == "token":
        return import_refresh_token(workspace=workspace, refresh_token=refresh_token)

    if mode == "password" and not use_chrome:
        print(
            "[aliyundrive] warning: password mode without --channel chrome; "
            "slider captcha often fails. Consider --mode qr"
        )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            **_launch_kwargs(headless=headless, use_chrome=use_chrome),
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4000)

        if page.url.startswith(DRIVE_URL_PREFIX) and mode == "password":
            print("[aliyundrive] clearing existing session for password re-login...")
            context.clear_cookies()
            page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(4000)
        if page.url.startswith(DRIVE_URL_PREFIX) and mode != "password":
            print("[aliyundrive] profile already logged in")
        elif not page.url.startswith(DRIVE_URL_PREFIX):
            if mode == "auto":
                mode = "desktop" if _has_desktop_quick_login(page) else "qr"

            _prompt_for_mode(page, mode)

            if mode == "desktop":
                oauth = _oauth_frame(page)
                if oauth is not None:
                    _try_desktop_quick_login(oauth)
                    page.wait_for_timeout(2000)
                if not page.url.startswith(DRIVE_URL_PREFIX):
                    passport = _passport_frame(page)
                    if passport is not None:
                        _ensure_qr_tab(passport)
                    _wait_for_drive(page)

            elif mode == "qr":
                passport = _passport_frame(page)
                if passport is not None:
                    _ensure_qr_tab(passport)
                _wait_for_drive(page)

            elif mode == "password":
                oauth = _oauth_frame(page)
                if oauth is not None and _has_desktop_quick_login(page):
                    print("[aliyundrive] trying desktop avatar before password form...")
                    _try_desktop_quick_login(oauth)
                    page.wait_for_timeout(2500)
                if not page.url.startswith(DRIVE_URL_PREFIX):
                    passport = _passport_frame(page)
                    if passport is None:
                        raise RuntimeError("passport mini_login iframe not found")
                    _switch_passport_to_account_login(passport)
                    if not _maybe_fill_credentials(passport, phone, password):
                        print("[aliyundrive] waiting for manual password login...")
                    _wait_for_drive(page)
            else:
                raise ValueError(f"unknown mode {mode!r}")
        else:
            print("[aliyundrive] profile already logged in")

        page.wait_for_timeout(1500)
        path = _save_session(context, page, workspace)
        print(f"[aliyundrive] profile dir: {profile_dir}")
        context.close()
        return path


def probe_login_form(*, workspace: Path = DEFAULT_WORKSPACE) -> None:
    profile_dir = workspace / ".playwright" / "aliyundrive-probe"
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)

        oauth = _oauth_frame(page)
        passport = _passport_frame(page)
        print("url:", page.url)
        print("oauth desktop-login:", oauth.locator(".desktop-login").count() if oauth else 0)
        print("passport frame:", bool(passport))
        if passport is not None:
            print("qr canvas:", passport.locator("#qrcode-img canvas").count())
            _switch_passport_to_account_login(passport)
            print("password fields:", passport.locator("#fm-login-id").count())
            print("captcha fields:", passport.locator("#nc_1_captcha_input").count())
        context.close()
    print("[aliyundrive] probe ok")


def _parse_args(argv: list[str]) -> tuple[str, bool, bool]:
    mode = os.environ.get("ALIYUN_DRIVE_LOGIN_MODE", "auto").strip().lower() or "auto"
    headless = False
    use_chrome = False
    for arg in argv:
        if arg == "--headless":
            headless = True
        elif arg == "--channel" and "chrome" in argv:
            use_chrome = True
        elif arg.startswith("--mode="):
            mode = arg.split("=", 1)[1].strip().lower()
        elif arg == "--mode" and argv.index(arg) + 1 < len(argv):
            mode = argv[argv.index(arg) + 1].strip().lower()
    if "--channel" in argv and "chrome" in argv:
        use_chrome = True
    return mode, headless, use_chrome


def main() -> int:
    if "--probe" in sys.argv:
        try:
            probe_login_form()
        except Exception as exc:
            print(f"[aliyundrive] probe failed: {exc}", file=sys.stderr)
            return 1
        return 0

    mode, headless, use_chrome = _parse_args(sys.argv[1:])
    try:
        login_with_profile(headless=headless, mode=mode, use_chrome=use_chrome)
    except Exception as exc:
        print(f"[aliyundrive] login failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
