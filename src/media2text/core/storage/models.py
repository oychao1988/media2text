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
    auto_record_override: str = "inherit"


@dataclass
class CreatorLiveSnapshotRow:
    creator_id: str
    is_live: int
    room_id: str | None
    title: str | None
    checked_at: str
    probe_error: str | None = None


@dataclass
class DesktopEventRow:
    id: str
    event_type: str
    creator_id: str | None
    payload_json: str | None
    created_at: str
    delivered_at: str | None


@dataclass
class DesktopChatThreadRow:
    id: str
    creator_id: str
    session_id: str | None
    title: str | None
    provider_name: str | None
    model: str
    context_mode: str
    created_at: str
    updated_at: str


@dataclass
class DesktopChatMessageRow:
    id: str
    thread_id: str
    role: str
    content: str
    thinking_text: str | None
    duration_ms: int | None
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
class DynamicRow:
    dynamic_id: str
    creator_id: str
    dynamic_type: str | None
    text: str | None
    refs_json: str | None
    image_count: int
    sync_status: str
    local_dir: str | None
    published_at: str | None
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
    transcribe_status: str | None = None
    cloud_upload_status: str | None = None
    cloud_file_id: str | None = None
    cloud_relative_path: str | None = None
    offline_streak: int = 0
    reconnect_attempts: int = 0
    segment_paths_json: str | None = None
    first_seen_live_at: str | None = None
    recording_started_at: str | None = None
    offline_since_at: str | None = None
    platform_live_started_at: str | None = None
    pipeline_mode: str | None = None


@dataclass
class MonitorTaskRow:
    id: str
    creator_id: str
    task_type: str
    payload_json: str | None
    priority: int
    status: str
    dedupe_key: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    attempt_count: int = 0
    attempt_count: int = 0


@dataclass
class PostProcessJobRow:
    id: str
    session_id: str
    creator_id: str
    mp4_path: str
    status: str
    stage: str | None
    error: str | None
    created_at: str
    updated_at: str

    @property
    def media_path(self) -> str:
        """FLV or MP4 absolute path (`mp4_path` column name retained for D4)."""
        return self.mp4_path


@dataclass
class PipelineEventRow:
    id: str
    session_id: str
    job_id: str | None
    stage: str
    status: str
    detail_json: str | None
    started_at: str
    ended_at: str | None
    duration_ms: int | None


@dataclass
class CloudUploadRow:
    id: str
    session_id: str
    creator_id: str
    platform: str
    file_name: str
    file_kind: str
    local_path: str | None
    cloud_file_id: str | None
    cloud_relative_path: str | None
    size: int | None
    pre_hash: str | None
    upload_status: str
    uploaded_at: str | None
    error: str | None
