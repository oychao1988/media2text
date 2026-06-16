"""Online validation for saved platform login sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from media2text.core.cloud.aliyundrive import load_token
from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, Media2TextError
from media2text.core.platform.bilibili.auth import session_exists as bilibili_session_exists
from media2text.core.platform.bilibili.auth import session_path as bilibili_session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage as bilibili_client
from media2text.core.platform.douyin.auth import session_exists as douyin_session_exists
from media2text.core.platform.douyin.auth import session_path as douyin_session_path

PlatformAuthStatus = Literal["ok", "missing", "expired", "unknown"]

_CACHE_TTL_SEC = 120.0
_cache: dict[str, tuple[float, dict]] = {}


@dataclass(frozen=True)
class PlatformAuthSnapshot:
    configured: bool
    valid: bool
    auth_required: bool
    status: PlatformAuthStatus
    error: str | None = None

    def as_dict(self) -> dict:
        out = {
            "configured": self.configured,
            "valid": self.valid,
            "auth_required": self.auth_required,
            "status": self.status,
        }
        if self.error:
            out["error"] = self.error
        return out


def invalidate_session_auth_cache(*, workspace: Path | None = None, platform: str | None = None) -> None:
    """Drop cached auth snapshots (e.g. after login)."""
    if workspace is None and platform is None:
        _cache.clear()
        return
    if workspace is not None and platform is not None:
        _cache.pop(_cache_key(platform, workspace), None)
        return
    prefix = f"{platform.strip().lower()}:" if platform else None
    ws_prefix = f":{workspace.resolve()}" if workspace else None
    for key in list(_cache):
        if prefix and not key.startswith(prefix):
            continue
        if ws_prefix and not key.endswith(ws_prefix):
            continue
        del _cache[key]


def _cache_key(platform: str, workspace: Path) -> str:
    return f"{platform.strip().lower()}:{workspace.resolve()}"


def platform_auth_snapshot(
    cfg: AppConfig,
    platform: str,
    *,
    validate: bool = True,
    refresh: bool = False,
) -> PlatformAuthSnapshot:
    key = platform.strip().lower()
    ws = cfg.ensure_workspace()
    cache_key = _cache_key(key, ws)
    if validate and not refresh:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_SEC:
            return PlatformAuthSnapshot(**hit[1])

    snap = _compute_snapshot(cfg, key, ws, validate=validate)
    if validate:
        _cache[cache_key] = (time.monotonic(), snap.__dict__)
    return snap


def _compute_snapshot(
    cfg: AppConfig,
    platform: str,
    workspace: Path,
    *,
    validate: bool,
) -> PlatformAuthSnapshot:
    if platform == "douyin":
        configured = douyin_session_exists(workspace)
        if not configured:
            return PlatformAuthSnapshot(
                configured=False,
                valid=False,
                auth_required=True,
                status="missing",
            )
        if not validate:
            return PlatformAuthSnapshot(
                configured=True,
                valid=True,
                auth_required=False,
                status="ok",
            )
        return _validate_douyin(douyin_session_path(workspace))

    if platform == "bilibili":
        configured = bilibili_session_exists(workspace)
        if not configured:
            return PlatformAuthSnapshot(
                configured=False,
                valid=False,
                auth_required=True,
                status="missing",
            )
        if not validate:
            return PlatformAuthSnapshot(
                configured=True,
                valid=True,
                auth_required=False,
                status="ok",
            )
        return _validate_bilibili(bilibili_session_path(workspace))

    if platform == "aliyundrive":
        return _validate_aliyundrive(cfg)

    return PlatformAuthSnapshot(
        configured=False,
        valid=False,
        auth_required=True,
        status="missing",
        error=f"unsupported platform: {platform}",
    )


def _validate_douyin(session_path: Path) -> PlatformAuthSnapshot:
    from media2text.core.platform.douyin.playwright_client import probe_douyin_session

    try:
        probe_douyin_session(session_path)
    except AuthRequired as exc:
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=True,
            status="expired",
            error=str(exc),
        )
    except TimeoutError as exc:
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=False,
            status="unknown",
            error=str(exc),
        )
    except Media2TextError as exc:
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=exc.code == "auth_required",
            status="unknown" if exc.code != "auth_required" else "expired",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=False,
            status="unknown",
            error=str(exc),
        )
    return PlatformAuthSnapshot(
        configured=True,
        valid=True,
        auth_required=False,
        status="ok",
    )


def _validate_bilibili(session_path: Path) -> PlatformAuthSnapshot:
    try:
        with bilibili_client(session_path, timeout=12.0) as client:
            response = client.get("https://api.bilibili.com/x/web-interface/nav")
            if response.status_code >= 400:
                raise httpx.HTTPError(f"nav http {response.status_code}")
            payload = response.json()
    except AuthRequired as exc:
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=True,
            status="expired",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=False,
            status="unknown",
            error=str(exc),
        )

    code = payload.get("code")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if code == 0 and data.get("isLogin"):
        return PlatformAuthSnapshot(
            configured=True,
            valid=True,
            auth_required=False,
            status="ok",
        )
    if code in (-101, -111):
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=True,
            status="expired",
            error="bilibili session not logged in",
        )
    return PlatformAuthSnapshot(
        configured=True,
        valid=False,
        auth_required=True,
        status="expired",
        error=f"bilibili nav code {code}",
    )


def _validate_aliyundrive(cfg: AppConfig) -> PlatformAuthSnapshot:
    path = cfg.aliyundrive_token_path()
    if not path.is_file():
        return PlatformAuthSnapshot(
            configured=False,
            valid=False,
            auth_required=True,
            status="missing",
        )
    try:
        token = load_token(path)
    except (OSError, ValueError) as exc:
        return PlatformAuthSnapshot(
            configured=True,
            valid=False,
            auth_required=True,
            status="expired",
            error=str(exc),
        )
    if token.get("refresh_token"):
        return PlatformAuthSnapshot(
            configured=True,
            valid=True,
            auth_required=False,
            status="ok",
        )
    return PlatformAuthSnapshot(
        configured=True,
        valid=False,
        auth_required=True,
        status="expired",
        error="missing refresh_token",
    )
