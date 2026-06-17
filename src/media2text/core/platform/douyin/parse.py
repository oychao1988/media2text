from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile

GALLERY_AWEME_TYPES = frozenset({2, 68, 150})


def _dig(data: Any, *keys: str) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def optional_platform_live_started_at(data: dict) -> str | None:
    """Parse platform live start time when API exposes unix seconds or ms."""
    for key in ("live_start_time", "start_time", "create_time", "open_time", "live_time"):
        raw = data.get(key)
        if raw is None:
            continue
        try:
            ts = int(raw)
        except (TypeError, ValueError):
            continue
        if ts > 1_000_000_000_000:
            ts //= 1000
        if ts <= 0:
            continue
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return None


def _user_sec_uid(user: dict) -> str | None:
    value = user.get("sec_uid") or user.get("secUid") or user.get("sec_user_id")
    return str(value) if value else None


def _find_user_by_sec_uid(data: Any, sec_uid: str, *, depth: int = 0) -> dict | None:
    if depth > 14:
        return None
    if isinstance(data, dict):
        if _user_sec_uid(data) == sec_uid and (data.get("nickname") or data.get("unique_id")):
            return data
        for value in data.values():
            found = _find_user_by_sec_uid(value, sec_uid, depth=depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data[:100]:
            found = _find_user_by_sec_uid(item, sec_uid, depth=depth + 1)
            if found:
                return found
    return None


def parse_user_profile(payload: dict, *, sec_uid: str | None = None) -> UserProfile:
    user = payload.get("user") or _dig(payload, "data", "user")
    if not user:
        raise ParseFailed("user missing in profile response")
    if sec_uid and _user_sec_uid(user) not in (None, sec_uid):
        raise ParseFailed("profile user sec_uid mismatch")

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


def parse_profile_html_user(payload: dict, *, sec_uid: str) -> UserProfile | None:
    """Parse target creator from profile page RENDER_DATA (not logged-in session user)."""
    user = _find_user_by_sec_uid(payload, sec_uid)
    if not user:
        return None
    try:
        return parse_user_profile({"user": user}, sec_uid=sec_uid)
    except ParseFailed:
        return None


def _coerce_room_data(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _flv_from_room_stream(room: dict) -> str | None:
    stream_url = room.get("stream_url") or {}
    flv_pull = stream_url.get("flv_pull_url")
    if isinstance(flv_pull, dict) and flv_pull:
        for key in ("HD1", "SD1", "FULL_HD1"):
            url = flv_pull.get(key)
            if isinstance(url, str) and url:
                return url
        return next((v for v in flv_pull.values() if isinstance(v, str) and v), None)
    if isinstance(flv_pull, str) and flv_pull:
        return flv_pull
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
    if live_status in (0, "0", False):
        is_live = False
    elif live_status in (1, "1", True):
        is_live = True
    else:
        is_live = False

    web_rid: str | None = None
    stream_flv_url: str | None = None
    title = user.get("nickname")
    room_data = _coerce_room_data(user.get("room_data"))
    if room_data:
        owner = room_data.get("owner")
        if isinstance(owner, dict):
            wr = owner.get("web_rid")
            if wr not in (None, "", 0, "0"):
                web_rid = str(wr)
        if room_data.get("status") == 2:
            stream_flv_url = _flv_from_room_stream(room_data)
            room_title = room_data.get("title")
            if isinstance(room_title, str) and room_title:
                title = room_title

    return LiveRoomInfo(
        room_id=room_id_str,
        is_live=is_live,
        stream_flv_url=stream_flv_url,
        web_rid=web_rid,
        title=title,
        platform_live_started_at=optional_platform_live_started_at(user),
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
        platform_live_started_at=optional_platform_live_started_at(room),
    )


def _live_room_from_profile_html(html: str) -> LiveRoomInfo | None:
    live_link = re.search(
        r"https?://live\.douyin\.com/(\d{6,})(?:[^\"']*)",
        html,
    )
    if not live_link:
        return None
    web_rid = live_link.group(1)
    fragment = live_link.group(0)
    room_id_match = re.search(r"room_id=(\d+)", fragment)
    room_id = room_id_match.group(1) if room_id_match else web_rid
    return LiveRoomInfo(room_id=room_id, web_rid=web_rid, is_live=True)


def parse_profile_html(html: str) -> LiveRoomInfo:
    """Parse live state from profile HTML.

    Prefer structured user state (RENDER_DATA / embedded JSON) over scraping the
    first ``live.douyin.com`` link, which is often a recommended stream and not
    the profile owner's room.
    """
    render = re.search(r'id="RENDER_DATA"[^>]*>([^<]+)', html)
    if render:
        try:
            data = json.loads(unquote(render.group(1)))
            user = _dig(data, "app", "user", "info") or _dig(data, "user", "user")
            if isinstance(user, dict):
                return parse_profile_live({"user": user})
        except (json.JSONDecodeError, ParseFailed):
            pass

    room_match = re.search(r'"room_id"\s*:\s*"?(\d+)"?', html)
    if room_match:
        room_id = room_match.group(1)
        if room_id in ("0", ""):
            return LiveRoomInfo(room_id=None, is_live=False)
        live_hint = re.search(r'"live_status"\s*:\s*(\d+)', html)
        is_live = live_hint.group(1) == "1" if live_hint else False
        return LiveRoomInfo(room_id=room_id, is_live=is_live)

    live_from_link = _live_room_from_profile_html(html)
    if live_from_link:
        return live_from_link

    return LiveRoomInfo(room_id=None, is_live=False)


def _aweme_post_list_field(payload: dict) -> list | None:
    if "aweme_list" in payload:
        value = payload.get("aweme_list")
        return value if isinstance(value, list) else None
    data = payload.get("data")
    if isinstance(data, dict) and "aweme_list" in data:
        value = data.get("aweme_list")
        return value if isinstance(value, list) else None
    return None


def _raise_platform_changed_aweme_post(payload: dict) -> None:
    status = payload.get("status_code")
    if status is None and isinstance(payload.get("data"), dict):
        status = payload["data"].get("status_code")
    if status is not None:
        try:
            if int(status) != 0:
                raise PlatformChanged(f"aweme post status_code={status}")
        except (TypeError, ValueError):
            pass
    if payload.get("status_msg") or _dig(payload, "data", "status_msg"):
        raise PlatformChanged("aweme post response missing aweme_list (status_msg present)")
    raise PlatformChanged("aweme post response missing aweme_list")


def _play_url_score(url: str) -> tuple[int, int]:
    watermarked = 0 if "watermark=0" in url else 1
    if "douyinvod.com" in url:
        cdn = 0
    elif "douyin.com" in url:
        cdn = 2
    else:
        cdn = 1
    return watermarked, cdn


def _pick_best_play_url(urls: list[str]) -> str | None:
    cleaned = [str(u) for u in urls if u]
    if not cleaned:
        return None
    return min(cleaned, key=_play_url_score)


def extract_aweme_download_url(row: dict) -> str | None:
    """Pick a direct play URL from aweme/post list item (sync-time cache)."""
    video = row.get("video")
    if not isinstance(video, dict):
        return None

    candidates: list[str] = []
    bit_rates = video.get("bit_rate")
    if isinstance(bit_rates, list):
        ranked: list[tuple[int, int, list[str]]] = []
        for entry in bit_rates:
            if not isinstance(entry, dict):
                continue
            play_addr = entry.get("play_addr")
            if not isinstance(play_addr, dict):
                continue
            try:
                bit_rate = int(entry.get("bit_rate") or 0)
            except (TypeError, ValueError):
                bit_rate = 0
            width = play_addr.get("width") or entry.get("width") or 0
            try:
                width = int(width)
            except (TypeError, ValueError):
                width = 0
            urls = [str(u) for u in (play_addr.get("url_list") or []) if u]
            if urls:
                ranked.append((bit_rate, width, urls))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for _, _, urls in ranked:
            candidates.extend(urls)

    play_addr = video.get("play_addr")
    if isinstance(play_addr, dict):
        candidates.extend(str(u) for u in (play_addr.get("url_list") or []) if u)

    return _pick_best_play_url(candidates)


def _extract_urls_from_source(source: Any) -> list[str]:
    if isinstance(source, dict):
        url_list = source.get("url_list") or source.get("urlList")
        if isinstance(url_list, list):
            return [str(u) for u in url_list if u]
    elif isinstance(source, list):
        return [str(u) for u in source if u]
    elif isinstance(source, str) and source:
        return [source]
    return []


def _media_url_priority(url: str) -> int:
    normalized = url.lower()
    path = (urlparse(url).path or "").lower()
    watermark_hints = (
        "tplv-dy-water",
        "dy-water",
        "owner_watermark",
        "watermark_image",
        "watermark=1",
        "playwm",
    )
    score = 100 if any(h in normalized for h in watermark_hints) else 0
    return score + (1 if ".webp" in path else 0)


def _collect_media_urls(*sources: Any) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for candidate in sorted(_extract_urls_from_source(source), key=_media_url_priority):
            if candidate in seen:
                continue
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _iter_gallery_items(row: dict) -> list[Any]:
    image_post = row.get("image_post_info")
    if isinstance(image_post, dict):
        for key in ("images", "image_list"):
            candidate = image_post.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
    images = row.get("images") or row.get("image_list") or []
    if isinstance(images, list):
        return images
    return []


def _has_video_source(row: dict) -> bool:
    video = row.get("video")
    if not isinstance(video, dict):
        return False
    if extract_aweme_download_url(row):
        return True
    return bool(
        video.get("vid")
        or (
            isinstance(video.get("download_addr"), dict)
            and video["download_addr"].get("uri")
        )
    )


def extract_gallery_image_urls(row: dict) -> list[str]:
    """Best-effort direct image URLs from aweme/post or aweme/detail item."""
    image_urls: list[str] = []
    for item in _iter_gallery_items(row):
        if not isinstance(item, dict):
            continue
        candidates = _collect_media_urls(
            item.get("watermark_free_download_url_list"),
            item.get("origin_image"),
            item.get("display_image"),
            item.get("download_url"),
            item.get("download_addr"),
            item.get("download_url_list"),
            item.get("owner_watermark_image"),
        )
        if candidates:
            image_urls.append(candidates[0])
    return image_urls


def detect_aweme_media_type(row: dict) -> str:
    if extract_gallery_image_urls(row):
        return "gallery"
    aweme_type = row.get("aweme_type")
    if isinstance(aweme_type, int) and aweme_type in GALLERY_AWEME_TYPES:
        if _has_video_source(row):
            return "video"
        return "gallery"
    return "video"


def parse_aweme_item(row: dict) -> AwemeItem:
    aweme_id = str(row.get("aweme_id") or "")
    media_type = detect_aweme_media_type(row)
    if media_type == "gallery":
        media_urls = extract_gallery_image_urls(row)
        return AwemeItem(
            aweme_id=aweme_id,
            title=row.get("desc") or row.get("title"),
            create_time=row.get("create_time"),
            media_type="gallery",
            media_urls=media_urls or None,
        )
    return AwemeItem(
        aweme_id=aweme_id,
        title=row.get("desc") or row.get("title"),
        create_time=row.get("create_time"),
        media_type="video",
        download_url=extract_aweme_download_url(row),
    )


def infer_image_extension(image_url: str) -> str:
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if not image_url:
        return ".jpg"
    image_path = (urlparse(image_url).path or "").lower()
    raw_suffix = Path(image_path).suffix.lower()
    if raw_suffix in allowed:
        return raw_suffix
    matches = re.findall(r"\.(?:jpe?g|png|webp|gif)(?=[^a-z0-9]|$)", image_path)
    if matches:
        return matches[-1].lower()
    return ".jpg"


def parse_aweme_detail_media(detail: dict) -> tuple[str, str | None, list[str] | None]:
    """Return (media_type, video_url, gallery_urls) from aweme_detail dict."""
    item = parse_aweme_item(detail)
    if item.media_type == "gallery":
        return "gallery", None, item.media_urls
    return "video", item.download_url, None


def parse_aweme_post_list(payload: dict) -> tuple[list[AwemeItem], str | None, bool]:
    if not isinstance(payload, dict):
        raise ParseFailed("aweme post payload must be object")

    aweme_list = _aweme_post_list_field(payload)
    if aweme_list is None:
        _raise_platform_changed_aweme_post(payload)
    assert aweme_list is not None
    items: list[AwemeItem] = []
    for row in aweme_list:
        aweme_id = str(row.get("aweme_id") or "")
        if not aweme_id:
            continue
        items.append(parse_aweme_item(row))
    max_cursor = payload.get("max_cursor") or _dig(payload, "data", "max_cursor")
    has_more = bool(payload.get("has_more") or _dig(payload, "data", "has_more"))
    return items, str(max_cursor) if max_cursor is not None else None, has_more


def parse_aweme_detail_url(payload: dict) -> str:
    detail = payload.get("aweme_detail") or _dig(payload, "data", "aweme_detail")
    if not detail:
        status = payload.get("status_code")
        if status is None and isinstance(payload.get("data"), dict):
            status = payload["data"].get("status_code")
        if status is not None:
            try:
                if int(status) != 0:
                    raise PlatformChanged(f"aweme detail status_code={status}")
            except (TypeError, ValueError):
                pass
        if payload.get("status_msg") or _dig(payload, "data", "status_msg"):
            raise PlatformChanged("aweme detail missing aweme_detail (status_msg present)")
        raise ParseFailed("aweme_detail missing")
    media_type, video_url, gallery_urls = parse_aweme_detail_media(detail)
    if media_type == "gallery":
        if not gallery_urls:
            raise ParseFailed("gallery images empty")
        return gallery_urls[0]
    if not video_url:
        url_list = _dig(detail, "video", "play_addr", "url_list") or []
        if not url_list:
            raise ParseFailed("play_addr.url_list empty")
        return str(url_list[0])
    return video_url


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
