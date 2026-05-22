from __future__ import annotations

from typing import Any

from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.douyin.models import LiveRoomInfo, UserProfile


def _dig(data: Any, *keys: str) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def check_api_code(payload: dict) -> None:
    code = payload.get("code")
    if code in (None, 0, "0"):
        return
    if code in (-101, -111):
        raise AuthRequired(f"bilibili api code {code}")
    if code in (-352, -400, -403):
        raise PlatformChanged(f"bilibili api code {code}: {payload.get('message', '')}")
    raise ParseFailed(f"bilibili api code {code}: {payload.get('message', '')}")


def parse_master_info(payload: dict) -> str | None:
    check_api_code(payload)
    room_id = _dig(payload, "data", "room_id")
    if room_id in (None, "", 0, "0"):
        return None
    return str(room_id)


def parse_room_info(payload: dict) -> LiveRoomInfo:
    check_api_code(payload)
    data = payload.get("data") or {}
    room_id = data.get("room_id")
    if room_id in (None, "", 0, "0"):
        return LiveRoomInfo(room_id=None, is_live=False)
    room_id_str = str(room_id)
    live_status = data.get("live_status")
    is_live = live_status in (1, 2, "1", "2")
    return LiveRoomInfo(
        room_id=room_id_str,
        is_live=is_live,
        title=data.get("title"),
    )


def parse_play_url(payload: dict) -> str:
    check_api_code(payload)
    data = payload.get("data") or {}
    durl = data.get("durl") or []
    if not durl:
        raise ParseFailed("playUrl durl missing")
    first = durl[0] if isinstance(durl[0], dict) else {}
    url = first.get("url")
    if not url:
        raise ParseFailed("playUrl stream url missing")
    return str(url)


def parse_space_acc_info(payload: dict) -> UserProfile:
    check_api_code(payload)
    data = payload.get("data") or {}
    name = data.get("name")
    face = data.get("face")
    sign = data.get("sign")
    fans = data.get("fans")
    if fans is not None:
        try:
            fans = int(fans)
        except (TypeError, ValueError):
            fans = None
    return UserProfile(
        display_name=str(name) if name else None,
        avatar_url=str(face) if face else None,
        signature=str(sign) if sign else None,
        follower_count=fans,
    )


def parse_space_live_room(payload: dict) -> LiveRoomInfo:
    """Parse x/space/acc/info live_room block."""
    check_api_code(payload)
    data = payload.get("data") or {}
    live_room = data.get("live_room") or {}
    room_id = live_room.get("roomid") or live_room.get("room_id")
    if room_id in (None, "", 0, "0"):
        return LiveRoomInfo(room_id=None, is_live=False)
    room_id_str = str(room_id)
    status = live_room.get("roomStatus") or live_room.get("live_status")
    is_live = status in (1, "1", True)
    return LiveRoomInfo(room_id=room_id_str, is_live=is_live, title=live_room.get("title"))
