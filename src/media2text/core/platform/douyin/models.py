from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiveRoomInfo:
    room_id: str | None
    is_live: bool
    stream_flv_url: str | None = None
    title: str | None = None


@dataclass
class AwemeItem:
    aweme_id: str
    title: str | None
    create_time: int | None
    media_type: str = "video"
