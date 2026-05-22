from __future__ import annotations

import httpx

from media2text.core.errors import ParseFailed
from media2text.core.platform.bilibili.parse import (
    check_api_code,
    parse_archive_cursor_list,
    parse_video_playurl,
)

ARCHIVE_CURSOR_URL = "https://app.biliapi.com/x/v2/space/archive/cursor"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"


def fetch_archive_page(
    client: httpx.Client | None,
    *,
    mid: str,
    max_cursor: str = "",
    count: int = 20,
) -> tuple[list, str | None, bool]:
    params: dict[str, str | int] = {
        "vmid": mid,
        "order": "pubdate",
        "ps": count,
        "platform": "web",
        "mobi_app": "web",
    }
    if max_cursor:
        params["aid"] = max_cursor

    if client:
        response = client.get(ARCHIVE_CURSOR_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    else:
        with httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
            },
            timeout=30.0,
            follow_redirects=True,
        ) as anon:
            response = anon.get(ARCHIVE_CURSOR_URL, params=params)
            response.raise_for_status()
            payload = response.json()

    return parse_archive_cursor_list(payload)


def resolve_video_download_url(client: httpx.Client, *, bvid: str) -> str:
    view_resp = client.get(VIEW_URL, params={"bvid": bvid})
    view_resp.raise_for_status()
    view_payload = view_resp.json()
    check_api_code(view_payload)
    data = view_payload.get("data") or {}
    cid = data.get("cid")
    if cid in (None, "", 0):
        raise ParseFailed(f"cid missing for bvid={bvid}")
    play_resp = client.get(
        PLAYURL_URL,
        params={
            "bvid": bvid,
            "cid": int(cid),
            "qn": 80,
            "fnval": 16,
            "fnver": 0,
            "fourk": 0,
        },
    )
    play_resp.raise_for_status()
    return parse_video_playurl(play_resp.json())
