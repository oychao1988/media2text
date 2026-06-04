from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from media2text.api.deps import get_cfg, spawn_auth_login
from media2text.core.cloud.aliyundrive import load_token
from media2text.core.config import AppConfig
from media2text.core.platform.bilibili.auth import session_exists as bilibili_session_exists
from media2text.core.platform.douyin.auth import session_exists as douyin_session_exists

router = APIRouter(prefix="/auth", tags=["auth"])

_VALID_PLATFORMS = frozenset({"douyin", "bilibili", "aliyundrive"})


def _aliyundrive_ok(cfg: AppConfig) -> bool:
    path = cfg.aliyundrive_token_path()
    if not path.is_file():
        return False
    try:
        return bool(load_token(path).get("refresh_token"))
    except (OSError, ValueError):
        return False


@router.get("/status")
def auth_status(cfg: AppConfig = Depends(get_cfg)) -> dict:
    ws = cfg.ensure_workspace()
    return {
        "ok": True,
        "platforms": {
            "douyin": {"configured": douyin_session_exists(ws)},
            "bilibili": {"configured": bilibili_session_exists(ws)},
            "aliyundrive": {"configured": _aliyundrive_ok(cfg)},
        },
    }


@router.post("/login/{platform}")
def auth_login(platform: str) -> dict:
    key = platform.strip().lower()
    if key not in _VALID_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail="platform must be douyin, bilibili, or aliyundrive",
        )
    return spawn_auth_login(key)
