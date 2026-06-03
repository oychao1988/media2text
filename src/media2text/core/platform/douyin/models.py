from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserProfile:
    display_name: str | None = None
    unique_id: str | None = None
    avatar_url: str | None = None
    signature: str | None = None
    follower_count: int | None = None


@dataclass
class LiveRoomInfo:
    room_id: str | None
    is_live: bool
    stream_flv_url: str | None = None
    title: str | None = None
    platform_live_started_at: str | None = None


@dataclass
class AwemeItem:
    aweme_id: str
    title: str | None
    create_time: int | None
    media_type: str = "video"
