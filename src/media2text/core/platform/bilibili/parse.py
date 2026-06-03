from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.bilibili.models_dynamic import ParsedDynamic
from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile
from media2text.core.platform.douyin.parse import optional_platform_live_started_at


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
    if code in (-352, -403):
        raise PlatformChanged(f"bilibili api code {code}: {payload.get('message', '')}")
    if code == -400:
        raise ParseFailed(f"bilibili api code {code}: {payload.get('message', '')}")
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
        platform_live_started_at=optional_platform_live_started_at(data),
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


def parse_arc_search_list(
    payload: dict,
) -> tuple[list[AwemeItem], str | None, bool]:
    """Parse api.bilibili.com x/space/arc/search response."""
    check_api_code(payload)
    data = payload.get("data") or {}
    list_block = data.get("list")
    vlist: list = []
    if isinstance(list_block, dict):
        vlist = list_block.get("vlist") or []
    elif isinstance(list_block, list):
        vlist = list_block

    items: list[AwemeItem] = []
    for raw in vlist:
        if not isinstance(raw, dict):
            continue
        bvid = raw.get("bvid")
        if not bvid:
            continue
        bvid_str = str(bvid).strip()
        if not bvid_str.startswith("BV"):
            continue
        created = raw.get("created")
        create_time: int | None = None
        if created is not None:
            try:
                create_time = int(created)
            except (TypeError, ValueError):
                create_time = None
        title = raw.get("title")
        items.append(
            AwemeItem(
                aweme_id=bvid_str,
                title=str(title) if title else None,
                create_time=create_time,
            )
        )

    page = data.get("page") or {}
    try:
        pn = int(page.get("pn") or 1)
        ps = int(page.get("ps") or 30)
        count = int(page.get("count") or 0)
    except (TypeError, ValueError):
        pn, ps, count = 1, 30, 0
    has_more = bool(count and pn * ps < count)
    next_cursor = str(pn + 1) if has_more else None
    return items, next_cursor, has_more


def parse_archive_cursor_list(
    payload: dict,
) -> tuple[list[AwemeItem], str | None, bool]:
    """Parse app.biliapi.com space/archive/cursor response."""
    check_api_code(payload)
    data = payload.get("data") or {}
    items: list[AwemeItem] = []
    last_aid: str | None = None
    for raw in data.get("item") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("goto") not in (None, "av", ""):
            continue
        bvid = raw.get("bvid")
        if not bvid:
            continue
        bvid_str = str(bvid).strip()
        if not bvid_str.startswith("BV"):
            continue
        ctime = raw.get("ctime")
        create_time: int | None = None
        if ctime is not None:
            try:
                create_time = int(ctime)
            except (TypeError, ValueError):
                create_time = None
        title = raw.get("title")
        items.append(
            AwemeItem(
                aweme_id=bvid_str,
                title=str(title) if title else None,
                create_time=create_time,
            )
        )
        param = raw.get("param")
        if param not in (None, ""):
            last_aid = str(param)
    has_more = bool(data.get("has_next"))
    next_cursor = last_aid if has_more and last_aid else None
    return items, next_cursor, has_more


def parse_video_playurl(payload: dict) -> str:
    """Parse x/player/playurl for VOD download."""
    return parse_play_url(payload)


def _normalize_dynamic_type(raw: str | None) -> str:
    if not raw:
        return "unknown"
    text = str(raw)
    if text.startswith("DYNAMIC_TYPE_"):
        text = text[len("DYNAMIC_TYPE_") :]
    return text.lower() or "unknown"


def _append_unique_url(urls: list[str], url: str | None) -> None:
    if not url:
        return
    u = str(url).strip()
    if u and u not in urls:
        urls.append(u)


def _extract_major_text(major: dict) -> str:
    parts: list[str] = []
    for key in ("opus", "archive", "draw", "common", "article"):
        block = major.get(key)
        if not isinstance(block, dict):
            continue
        for field in ("title", "desc", "summary", "content"):
            val = block.get(field)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
            elif isinstance(val, dict):
                text = val.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    return "\n\n".join(parts).strip()


def _extract_major_images(major: dict) -> list[str]:
    urls: list[str] = []
    major_type = major.get("type")
    opus = major.get("opus")
    if isinstance(opus, dict):
        for pic in opus.get("pics") or []:
            if isinstance(pic, dict):
                _append_unique_url(urls, pic.get("url"))
    draw = major.get("draw")
    if isinstance(draw, dict):
        for pic in draw.get("items") or draw.get("pics") or []:
            if isinstance(pic, dict):
                _append_unique_url(urls, pic.get("src") or pic.get("url"))
    archive = major.get("archive")
    if isinstance(archive, dict):
        _append_unique_url(urls, archive.get("cover"))
    common = major.get("common")
    if isinstance(common, dict):
        _append_unique_url(urls, common.get("cover"))
    if major_type == "MAJOR_TYPE_PICTURES":
        pictures = major.get("pictures")
        if isinstance(pictures, dict):
            for pic in pictures.get("pics") or []:
                if isinstance(pic, dict):
                    _append_unique_url(urls, pic.get("url"))
    return urls


def _parse_dynamic_item(item: dict) -> ParsedDynamic | None:
    dynamic_id = item.get("id_str")
    if not dynamic_id:
        return None
    dynamic_id = str(dynamic_id)
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    pub_ts = author.get("pub_ts")
    published_at: str | None = None
    create_ts: int | None = None
    if pub_ts is not None:
        try:
            create_ts = int(pub_ts)
            published_at = datetime.fromtimestamp(create_ts, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            published_at = None
            create_ts = None

    module_dynamic = modules.get("module_dynamic") or {}
    desc = module_dynamic.get("desc")
    text_parts: list[str] = []
    if isinstance(desc, str) and desc.strip():
        text_parts.append(desc.strip())
    elif isinstance(desc, dict):
        dtext = desc.get("text")
        if isinstance(dtext, str) and dtext.strip():
            text_parts.append(dtext.strip())

    major = module_dynamic.get("major") or {}
    if isinstance(major, dict):
        major_text = _extract_major_text(major)
        if major_text:
            text_parts.append(major_text)

    image_urls = _extract_major_images(major) if isinstance(major, dict) else []

    bvid: str | None = None
    opus_id: str | None = None
    if isinstance(major, dict):
        archive = major.get("archive")
        if isinstance(archive, dict):
            raw_bvid = archive.get("bvid")
            if raw_bvid:
                bvid = str(raw_bvid).strip()
        opus = major.get("opus")
        if isinstance(opus, dict):
            jump = opus.get("jump_url") or ""
            if "/opus/" in str(jump):
                opus_id = str(jump).split("/opus/")[-1].split("?")[0].strip("/")
            if not opus_id and dynamic_id:
                opus_id = dynamic_id

    return ParsedDynamic(
        dynamic_id=dynamic_id,
        dynamic_type=_normalize_dynamic_type(item.get("type")),
        text="\n\n".join(text_parts).strip(),
        image_urls=image_urls,
        bvid=bvid,
        opus_id=opus_id,
        published_at=published_at,
        pub_ts=create_ts,
    )


def parse_dynamic_feed(
    payload: dict,
) -> tuple[list[ParsedDynamic], str | None, bool]:
    """Parse polymer web-dynamic feed/space response."""
    check_api_code(payload)
    data = payload.get("data") or {}
    items: list[ParsedDynamic] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_dynamic_item(raw)
        if parsed:
            items.append(parsed)
    has_more = bool(data.get("has_more"))
    offset = data.get("offset")
    next_offset = str(offset) if has_more and offset not in (None, "") else None
    return items, next_offset, has_more


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
