"""Proxy creator avatar images for desktop CSP (loopback img-src only)."""

from __future__ import annotations

import httpx

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_REFERER_BY_PLATFORM = {
    "douyin": "https://www.douyin.com/",
    "bilibili": "https://www.bilibili.com/",
}


def fetch_creator_avatar(url: str, *, platform: str) -> tuple[bytes, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Referer": _REFERER_BY_PLATFORM.get(platform, "https://www.douyin.com/"),
    }
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"
    return resp.content, content_type
