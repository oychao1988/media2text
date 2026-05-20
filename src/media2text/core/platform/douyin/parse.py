from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile


def _dig(data: Any, *keys: str) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def parse_user_profile(payload: dict) -> UserProfile:
    user = payload.get("user") or _dig(payload, "data", "user")
    if not user:
        raise ParseFailed("user missing in profile response")

    avatar_url = None
    avatar_thumb = user.get("avatar_thumb") or user.get("avatar_larger") or {}
    if isinstance(avatar_thumb, dict):
        url_list = avatar_thumb.get("url_list") or []
        if url_list:
            avatar_url = str(url_list[0])

    follower = user.get("follower_count")
    if follower is not None:
        try:
            follower = int(follower)
        except (TypeError, ValueError):
            follower = None

    return UserProfile(
        display_name=user.get("nickname"),
        unique_id=user.get("unique_id") or user.get("short_id"),
        avatar_url=avatar_url,
        signature=user.get("signature"),
        follower_count=follower,
    )


def parse_profile_html_user(payload: dict) -> UserProfile | None:
    user = _dig(payload, "app", "user", "info") or _dig(payload, "user", "user")
    if not isinstance(user, dict):
        return None
    try:
        return parse_user_profile({"user": user})
    except ParseFailed:
        return None


def parse_profile_live(payload: dict) -> LiveRoomInfo:
    user = payload.get("user") or _dig(payload, "data", "user")
    if not user:
        raise ParseFailed("user missing in profile response")

    room_id = user.get("room_id") or user.get("room_id_str")
    if room_id in (None, "", 0, "0"):
        return LiveRoomInfo(room_id=None, is_live=False)

    room_id_str = str(room_id)
    live_status = user.get("live_status")
    is_live = live_status in (1, "1", True) or bool(room_id_str)

    return LiveRoomInfo(
        room_id=room_id_str,
        is_live=is_live,
        title=user.get("nickname"),
    )


def parse_reflow_room(payload: dict) -> LiveRoomInfo:
    room = payload.get("room") or _dig(payload, "data", "room")
    if not room:
        raise ParseFailed("room missing in reflow response")

    status = room.get("status")
    is_live = status == 2
    room_id = str(room.get("id_str") or room.get("id") or "")
    stream_flv_url = None
    stream_url = room.get("stream_url") or {}
    flv_pull = stream_url.get("flv_pull_url")
    if isinstance(flv_pull, dict) and flv_pull:
        stream_flv_url = next(iter(flv_pull.values()), None)
    elif isinstance(flv_pull, str):
        stream_flv_url = flv_pull

    return LiveRoomInfo(
        room_id=room_id or None,
        is_live=is_live,
        stream_flv_url=stream_flv_url,
        title=_dig(room, "owner", "nickname"),
    )


def _live_room_from_profile_html(html: str) -> LiveRoomInfo | None:
    live_link = re.search(
        r"https?://live\.douyin\.com/(\d{6,})(?:[/?\"&#]|$)",
        html,
    )
    if live_link:
        return LiveRoomInfo(room_id=live_link.group(1), is_live=True)
    return None


def parse_profile_html(html: str) -> LiveRoomInfo:
    live_from_link = _live_room_from_profile_html(html)
    if live_from_link:
        return live_from_link

    render = re.search(r'id="RENDER_DATA"[^>]*>([^<]+)', html)
    if render:
        try:
            data = json.loads(unquote(render.group(1)))
            user = _dig(data, "app", "user", "info") or _dig(data, "user", "user")
            if isinstance(user, dict):
                info = parse_profile_live({"user": user})
                if info.is_live and info.room_id:
                    return info
        except (json.JSONDecodeError, ParseFailed):
            pass

    room_match = re.search(r'"room_id"\s*:\s*"?(\d+)"?', html)
    if not room_match:
        return LiveRoomInfo(room_id=None, is_live=False)

    room_id = room_match.group(1)
    live_hint = re.search(r'"live_status"\s*:\s*(\d+)', html)
    is_live = live_hint.group(1) == "1" if live_hint else True
    return LiveRoomInfo(room_id=room_id, is_live=is_live)


def parse_aweme_post_list(payload: dict) -> tuple[list[AwemeItem], str | None, bool]:
    aweme_list = payload.get("aweme_list") or _dig(payload, "data", "aweme_list") or []
    items: list[AwemeItem] = []
    for row in aweme_list:
        aweme_id = str(row.get("aweme_id") or "")
        if not aweme_id:
            continue
        items.append(
            AwemeItem(
                aweme_id=aweme_id,
                title=row.get("desc") or row.get("title"),
                create_time=row.get("create_time"),
                media_type="video",
            )
        )
    max_cursor = payload.get("max_cursor") or _dig(payload, "data", "max_cursor")
    has_more = bool(payload.get("has_more") or _dig(payload, "data", "has_more"))
    return items, str(max_cursor) if max_cursor is not None else None, has_more


def parse_aweme_detail_url(payload: dict) -> str:
    detail = payload.get("aweme_detail") or _dig(payload, "data", "aweme_detail")
    if not detail:
        raise ParseFailed("aweme_detail missing")
    url_list = _dig(detail, "video", "play_addr", "url_list") or []
    if not url_list:
        raise ParseFailed("play_addr.url_list empty")
    return str(url_list[0])


def map_http_error(status: int, body: str) -> Exception:
    if status in (401, 403):
        return AuthRequired(f"http {status}")
    if status == 429:
        from media2text.core.errors import RateLimited

        return RateLimited(f"http {status}")
    if status >= 500:
        return ParseFailed(f"server error {status}")
    if "blocked" in body.lower():
        return AuthRequired("account blocked")
    return ParseFailed(f"http {status}: {body[:200]}")
