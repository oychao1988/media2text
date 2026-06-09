from __future__ import annotations

import json

import httpx

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.platform.douyin.parse import map_http_error, parse_profile_html, parse_profile_live

_PROFILE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def _profile_api_headers(sec_uid: str) -> dict[str, str]:
    profile_url = f"https://www.douyin.com/user/{sec_uid}"
    return {
        "User-Agent": _PROFILE_UA,
        "Referer": profile_url,
        "Origin": "https://www.douyin.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }


def fetch_profile_page(client: httpx.Client, sec_uid: str) -> str:
    url = f"https://www.douyin.com/user/{sec_uid}"
    response = client.get(url)
    if response.status_code >= 400:
        raise map_http_error(response.status_code, response.text)
    return response.text


def fetch_profile_api(client: httpx.Client, sec_uid: str) -> dict:
    response = client.get(
        "https://www.douyin.com/aweme/v1/web/user/profile/other/",
        params={
            "sec_user_id": sec_uid,
            "publish_video_strategy_type": "2",
            "personal_center_strategy": "1",
        },
        headers=_profile_api_headers(sec_uid),
    )
    if response.status_code >= 400:
        raise map_http_error(response.status_code, response.text)
    text = response.text.strip()
    if not text or text[0] not in "{[":
        if response.headers.get("x-vc-bdturing-parameters"):
            raise ParseFailed(
                "profile API blocked by douyin verify (unsigned httpx); "
                "use browser page intercept"
            )
        raise ParseFailed("profile API returned non-JSON body")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ParseFailed("profile API JSON decode failed") from exc


def resolve_live_via_http(client: httpx.Client, sec_uid: str) -> LiveRoomInfo:
    """HTTP fallback for live probe when Playwright is unavailable."""
    info: LiveRoomInfo | None = None
    try:
        payload = fetch_profile_api(client, sec_uid)
        info = parse_profile_live(payload)
        if info.is_live and info.room_id:
            return info
    except (ParseFailed, AuthRequired, httpx.HTTPError, json.JSONDecodeError):
        pass

    html = fetch_profile_page(client, sec_uid)
    html_info = parse_profile_html(html)
    if html_info.is_live and html_info.room_id:
        return html_info
    return info if info is not None else html_info
