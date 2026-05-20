from dataclasses import dataclass


@dataclass
class CreatorRow:
    id: str
    platform: str
    sec_uid: str
    display_name: str | None
    profile_url: str | None
    watch_live: int
    monitor_enabled: int
    unique_id: str | None
    avatar_url: str | None
    signature: str | None
    follower_count: int | None
    profile_synced_at: str | None
    created_at: str


@dataclass
class AwemeRow:
    aweme_id: str
    creator_id: str
    title: str | None
    create_time: int | None
    media_type: str | None
    sync_status: str
    local_path: str | None
    transcribe_status: str | None
    transcript_path: str | None
    updated_at: str


@dataclass
class LiveSessionRow:
    id: str
    creator_id: str
    room_id: str | None
    ffmpeg_pid: int | None
    started_at: str
    ended_at: str | None
    local_path: str | None
    temp_path: str | None
    status: str
    error: str | None
