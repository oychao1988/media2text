from __future__ import annotations

import json

import httpx

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.platform.douyin.parse import map_http_error, parse_profile_html, parse_profile_live


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
    )
    if response.status_code >= 400:
        raise map_http_error(response.status_code, response.text)
    text = response.text.strip()
    if not text or text[0] not in "{[":
        raise ParseFailed("profile API returned non-JSON body")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ParseFailed("profile API JSON decode failed") from exc


def resolve_live_via_http(client: httpx.Client, sec_uid: str) -> LiveRoomInfo:
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
