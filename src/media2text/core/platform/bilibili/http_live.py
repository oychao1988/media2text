from __future__ import annotations

import httpx

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.bilibili.parse import (
    check_api_code,
    parse_master_info,
    parse_play_url,
    parse_room_info,
    parse_space_acc_info,
    parse_space_live_room,
)
from media2text.core.platform.douyin.models import LiveRoomInfo, UserProfile

LIVE_API = "https://api.live.bilibili.com"
SPACE_API = "https://api.bilibili.com"


def fetch_master_room_id(client: httpx.Client, mid: str) -> str | None:
    response = client.get(
        f"{LIVE_API}/live_user/v1/Master/info",
        params={"uid": mid},
    )
    if response.status_code >= 400:
        raise ParseFailed(f"master info http {response.status_code}")
    payload = response.json()
    return parse_master_info(payload)


def fetch_room_info(client: httpx.Client, room_id: str) -> LiveRoomInfo:
    response = client.get(
        f"{LIVE_API}/room/v1/Room/get_info",
        params={"room_id": room_id},
    )
    if response.status_code >= 400:
        raise ParseFailed(f"room get_info http {response.status_code}")
    return parse_room_info(response.json())


def fetch_play_url(client: httpx.Client, room_id: str) -> str:
    response = client.get(
        f"{LIVE_API}/room/v1/Room/playUrl",
        params={"cid": room_id, "platform": "web", "quality": 4},
    )
    if response.status_code >= 400:
        raise ParseFailed(f"playUrl http {response.status_code}")
    return parse_play_url(response.json())


def fetch_space_profile(client: httpx.Client, mid: str) -> UserProfile:
    response = client.get(
        f"{SPACE_API}/x/space/acc/info",
        params={"mid": mid},
    )
    if response.status_code >= 400:
        raise ParseFailed(f"space acc info http {response.status_code}")
    return parse_space_acc_info(response.json())


def resolve_live_via_http(client: httpx.Client, mid: str) -> LiveRoomInfo:
    try:
        space_resp = client.get(
            f"{SPACE_API}/x/space/acc/info",
            params={"mid": mid},
        )
        if space_resp.status_code < 400:
            payload = space_resp.json()
            check_api_code(payload)
            info = parse_space_live_room(payload)
            if info.is_live and info.room_id:
                try:
                    info.stream_flv_url = fetch_play_url(client, info.room_id)
                except (ParseFailed, AuthRequired):
                    pass
                return info
    except (ParseFailed, AuthRequired):
        raise
    except httpx.HTTPError as exc:
        raise ParseFailed(f"space acc info failed: {exc}") from exc

    room_id = fetch_master_room_id(client, mid)
    if not room_id:
        return LiveRoomInfo(room_id=None, is_live=False)

    info = fetch_room_info(client, room_id)
    if info.is_live and info.room_id:
        try:
            info.stream_flv_url = fetch_play_url(client, info.room_id)
        except (ParseFailed, AuthRequired):
            pass
    return info
