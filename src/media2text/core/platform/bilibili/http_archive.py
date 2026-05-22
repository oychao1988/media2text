from __future__ import annotations

import time

import httpx

from media2text.core.errors import ParseFailed
from media2text.core.platform.bilibili.parse import (
    check_api_code,
    parse_arc_search_list,
    parse_archive_cursor_list,
    parse_video_playurl,
)

ARC_SEARCH_URL = "https://api.bilibili.com/x/space/arc/search"
ARCHIVE_CURSOR_URL = "https://app.biliapi.com/x/v2/space/archive/cursor"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


def _page_from_cursor(max_cursor: str) -> int:
    if max_cursor and str(max_cursor).isdigit():
        return int(max_cursor)
    return 1


def fetch_arc_search_page(
    client: httpx.Client,
    *,
    mid: str,
    max_cursor: str = "",
    count: int = 30,
) -> tuple[list, str | None, bool]:
    pn = _page_from_cursor(max_cursor)
    ps = max(1, min(int(count), 50))
    params = {
        "mid": mid,
        "pn": pn,
        "ps": ps,
        "order": "pubdate",
    }
    headers = {
        **_DEFAULT_HEADERS,
        "Referer": f"https://space.bilibili.com/{mid}/video",
        "Origin": "https://space.bilibili.com",
    }
    max_attempts = 6
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        response = client.get(ARC_SEARCH_URL, params=params, headers=headers)
        if response.status_code == 412 and attempt + 1 < max_attempts:
            time.sleep(1.0 + attempt)
            continue
        if response.status_code >= 400:
            response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            last_err = exc
            if attempt + 1 < max_attempts:
                time.sleep(1.0 + attempt)
                continue
            raise
        code = payload.get("code")
        if code == -799 and attempt + 1 < max_attempts:
            time.sleep(min(30.0, 3.0 * (2**attempt)))
            continue
        return parse_arc_search_list(payload)
    if last_err:
        raise last_err
    raise ParseFailed("arc/search failed after retries")


def fetch_archive_cursor_page(
    client: httpx.Client | None,
    *,
    mid: str,
    max_cursor: str = "",
    count: int = 20,
) -> tuple[list, str | None, bool]:
    """Legacy app.biliapi.com cursor API (often returns -400)."""
    params: dict[str, str | int] = {
        "vmid": mid,
        "order": "pubdate",
        "ps": count,
        "platform": "web",
        "mobi_app": "web",
    }
    if max_cursor and not str(max_cursor).isdigit():
        params["aid"] = max_cursor

    if client:
        response = client.get(ARCHIVE_CURSOR_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    else:
        with httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        ) as anon:
            response = anon.get(ARCHIVE_CURSOR_URL, params=params)
            response.raise_for_status()
            payload = response.json()

    return parse_archive_cursor_list(payload)


def fetch_archive_page(
    client: httpx.Client | None,
    *,
    mid: str,
    max_cursor: str = "",
    count: int = 30,
) -> tuple[list, str | None, bool]:
    """List UP archives; web arc/search (session or anonymous)."""
    if client is not None:
        return fetch_arc_search_page(
            client, mid=mid, max_cursor=max_cursor, count=count
        )

    try:
        return fetch_archive_cursor_page(
            None, mid=mid, max_cursor=max_cursor, count=count
        )
    except ParseFailed:
        with httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        ) as anon:
            return fetch_arc_search_page(
                anon, mid=mid, max_cursor=max_cursor, count=count
            )


def resolve_video_download_url(client: httpx.Client, *, bvid: str) -> str:
    view_resp = client.get(
        VIEW_URL,
        params={"bvid": bvid},
        headers={**_DEFAULT_HEADERS, "Referer": f"https://www.bilibili.com/video/{bvid}"},
    )
    view_resp.raise_for_status()
    view_payload = view_resp.json()
    check_api_code(view_payload)
    data = view_payload.get("data") or {}
    cid = data.get("cid")
    if cid in (None, "", 0):
        raise ParseFailed(f"cid missing for bvid={bvid}")

    referer = f"https://www.bilibili.com/video/{bvid}"
    play_params = {
        "bvid": bvid,
        "cid": int(cid),
        "qn": 64,
        "fnval": 1,
        "fnver": 0,
        "fourk": 0,
    }
    play_resp = client.get(
        PLAYURL_URL,
        params=play_params,
        headers={**_DEFAULT_HEADERS, "Referer": referer},
    )
    play_resp.raise_for_status()
    play_payload = play_resp.json()
    try:
        return parse_video_playurl(play_payload)
    except ParseFailed:
        pass

    # Some streams only expose DASH; try merging first video+audio when durl absent.
    dash_resp = client.get(
        PLAYURL_URL,
        params={**play_params, "fnval": 16},
        headers={**_DEFAULT_HEADERS, "Referer": referer},
    )
    dash_resp.raise_for_status()
    dash_payload = dash_resp.json()
    check_api_code(dash_payload)
    dash_data = dash_payload.get("data") or {}
    durl = dash_data.get("durl") or []
    if durl:
        first = durl[0] if isinstance(durl[0], dict) else {}
        url = first.get("url")
        if url:
            return str(url)
    raise ParseFailed(f"playUrl durl missing for bvid={bvid}")
