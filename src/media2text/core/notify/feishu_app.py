from __future__ import annotations

import time
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger()

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def get_tenant_access_token(*, app_id: str, app_secret: str, timeout_sec: float = 10.0) -> str | None:
    cache_key = app_id
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, json={"app_id": app_id, "app_secret": app_secret})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("feishu_token_failed", error=str(exc))
        return None
    if data.get("code") != 0:
        log.warning("feishu_token_rejected", code=data.get("code"), msg=data.get("msg"))
        return None
    token = data.get("tenant_access_token")
    expire = int(data.get("expire", 7200))
    if not token:
        return None
    _TOKEN_CACHE[cache_key] = (token, time.time() + max(expire - 120, 60))
    return token


def upload_image(
    *,
    image_path: Path,
    app_id: str,
    app_secret: str,
    timeout_sec: float = 30.0,
) -> str | None:
    token = get_tenant_access_token(app_id=app_id, app_secret=app_secret, timeout_sec=timeout_sec)
    if not token:
        return None
    url = "https://open.feishu.cn/open-apis/im/v1/images"
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            with image_path.open("rb") as fh:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    files={"image": (image_path.name, fh, "application/octet-stream")},
                    data={"image_type": "message"},
                )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("feishu_image_upload_failed", path=str(image_path), error=str(exc))
        return None
    if data.get("code") != 0:
        log.warning(
            "feishu_image_upload_rejected",
            code=data.get("code"),
            msg=data.get("msg"),
        )
        return None
    key = (data.get("data") or {}).get("image_key")
    return key if isinstance(key, str) else None
