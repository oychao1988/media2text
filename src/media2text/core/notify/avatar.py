from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger()


def download_avatar_image(url: str, *, timeout_sec: float = 15.0) -> Path | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            suffix = ".jpg"
            ctype = resp.headers.get("content-type", "")
            if "png" in ctype:
                suffix = ".png"
            elif "webp" in ctype:
                suffix = ".webp"
            tmp = Path(tempfile.gettempdir()) / f"media2text-avatar-{abs(hash(url)) % 10**8}{suffix}"
            tmp.write_bytes(resp.content)
            if tmp.stat().st_size == 0:
                tmp.unlink(missing_ok=True)
                return None
            return tmp
    except Exception as exc:  # noqa: BLE001
        log.warning("avatar_download_failed", url=url[:80], error=str(exc))
        return None
