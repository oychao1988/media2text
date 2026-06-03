from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings

from media2text.core.errors import ConfigError


class DouyinPlatformConfig(BaseModel):
    poll_interval_sec: int = 60
    download_concurrency: int = 3
    max_sync_pages: int = 0


class BilibiliPlatformConfig(BaseModel):
    live_poll_interval_sec: int = 0
    archive_poll_interval_sec: int = 300
    dynamic_poll_interval_sec: int = 120
    dynamic_poll_interval_min_sec: int = 5
    max_sync_pages: int = 0
    max_dynamic_sync_pages: int = 0
    download_concurrency: int = 3
    download_dynamic_images: bool = True
    max_dynamic_images_per_item: int = 50


class PlatformsConfig(BaseModel):
    douyin: DouyinPlatformConfig = Field(default_factory=DouyinPlatformConfig)
    bilibili: BilibiliPlatformConfig = Field(default_factory=BilibiliPlatformConfig)

    @model_validator(mode="after")
    def _validate_bilibili_dynamic_poll(self) -> PlatformsConfig:
        b = self.bilibili
        min_sec = b.dynamic_poll_interval_min_sec
        if b.dynamic_poll_interval_sec < min_sec:
            raise ConfigError(
                f"platforms.bilibili.dynamic_poll_interval_sec must be >= {min_sec}"
            )
        return self


class MonitorConfig(BaseModel):
    live_poll_interval_sec: int = 60
    vod_poll_interval_sec: int = 300
    max_creators_per_vod_tick: int = 0
    profile_stale_days: int = 7


class LiveConfig(BaseModel):
    transcribe_on_complete: bool = False
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_stop_timeout_sec: int = 30
    temp_format: str = "flv"
    live_poll_interval_sec: int = 10
    offline_confirm_sec: int = 45
    offline_confirm_polls: int = 3  # deprecated; logic uses offline_confirm_sec
    ffmpeg_exit_recheck: bool = True
    max_reconnect_attempts: int = 2
    min_recording_sec_before_offline_end: int = 45
    post_process_poll_interval_sec: int = 10
    post_process_max_parallel: int = 0
    post_process_stale_running_sec: int = 3600
    scan_concurrency: int = 4
    # During active recording, treat profile API offline as inconclusive when ffmpeg
    # is still writing or the room reflow API reports live (Douyin profile often flakes).
    offline_trust_recording_signals: bool = True


class WhisperConfig(BaseModel):
    model: str = "medium"
    device: str = "auto"
    compute_type: str = "int8"
    vad_filter: bool = True
    extract_audio: bool = True


class OpenAIConfig(BaseModel):
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "whisper-1"
    base_url: str | None = None


class DeepgramConfig(BaseModel):
    api_key_env: str = "DEEPGRAM_API_KEY"
    model: str = "nova-3"
    extract_audio: bool = True
    smart_format: bool = True
    punctuate: bool = True
    utterances: bool = True
    diarize: bool = False
    timeout_sec: float = 600.0


class TranscribeConfig(BaseModel):
    engine: str = "whisper"
    language: str = "zh"
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    deepgram: DeepgramConfig = Field(default_factory=DeepgramConfig)


class SummarizeLlmProviderConfig(BaseModel):
    """One OpenAI-compatible endpoint with its own base_url, keys, and models."""

    name: str = ""
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key_envs: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


def _default_summarize_providers() -> list[SummarizeLlmProviderConfig]:
    return [
        SummarizeLlmProviderConfig(
            name="nvidia",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key_envs=["NVIDIA_API_KEY"],
            models=["deepseek-ai/deepseek-v4-pro"],
        )
    ]


class SummarizeLlmConfig(BaseModel):
    providers: list[SummarizeLlmProviderConfig] = Field(
        default_factory=_default_summarize_providers
    )
    temperature: float = 0.2
    top_p: float = 0.95
    max_output_tokens: int = 4096
    thinking: bool = False
    log_token_usage: bool = True


class SummarizeChunkConfig(BaseModel):
    max_chars: int = 24000
    minutes: float = 30.0


class SummarizeMergeConfig(BaseModel):
    auto_merge_after_parts: bool = False


class SummarizeConfig(BaseModel):
    enabled: bool = False
    engine: str = "openai"
    on_transcribe_complete: bool = False
    default_profile: str = "auto"
    merge_gap_minutes: int = 60
    merge_date_tz: str = "UTC"
    max_files_per_run: int = 0
    llm: SummarizeLlmConfig = Field(default_factory=SummarizeLlmConfig)
    chunk: SummarizeChunkConfig = Field(default_factory=SummarizeChunkConfig)
    merge: SummarizeMergeConfig = Field(default_factory=SummarizeMergeConfig)


class NotifyEventsConfig(BaseModel):
    live_started: bool = True
    live_start_failed: bool = True
    live_ended: bool = True
    new_aweme: bool = True
    new_archive: bool = True
    new_dynamic: bool = True
    recording_completed: bool = True
    transcribe_completed: bool = True
    summarize_completed: bool = True
    upload_completed: bool = True
    upload_failed: bool = True
    upload_skipped: bool = True
    upload_cleanup: bool = True


class AliyunDriveRollingCleanupConfig(BaseModel):
    max_delete_per_round: int = 20


class AliyunDriveConfig(BaseModel):
    enabled: bool = False
    token_path: str = "sessions/aliyundrive.token.json"
    parent_file_id: str = "root"
    root_folder: str = "media2text"
    creator_key: str = "nickname"
    min_free_bytes: int = 5 * 1024 * 1024 * 1024
    upload_on_live_complete: bool = True
    upload_transcripts: bool = True
    delete_local_after_upload: bool = True
    on_insufficient_space: str = "rolling_cleanup"
    rolling_cleanup: AliyunDriveRollingCleanupConfig = Field(
        default_factory=AliyunDriveRollingCleanupConfig
    )
    upload_retries: int = 2


class NotifyFeishuConfig(BaseModel):
    enabled: bool = True
    webhook_url: str = ""
    webhook_url_env: str = "NOTIFY_FEISHU_WEBHOOK_URL"
    timeout_sec: float = 10.0


class NotifyConfig(BaseModel):
    enabled: bool = False
    sound: bool = True
    sound_path: str = ""
    events: NotifyEventsConfig = Field(default_factory=NotifyEventsConfig)
    feishu: NotifyFeishuConfig = Field(default_factory=NotifyFeishuConfig)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_dotenv_file() -> Path | None:
    """Load `.env` from project root into os.environ (does not override existing vars)."""
    env_path = _project_root() / ".env"
    if not env_path.is_file():
        return None
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    load_dotenv(env_path, override=False)
    return env_path


class AppConfig(BaseSettings):
    workspace: Path = Path("./data")
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    summarize: SummarizeConfig = Field(default_factory=SummarizeConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    aliyundrive: AliyunDriveConfig = Field(default_factory=AliyunDriveConfig)

    def aliyundrive_token_path(self) -> Path:
        return self.ensure_workspace() / self.aliyundrive.token_path

    @classmethod
    def load(cls) -> AppConfig:
        load_dotenv_file()
        path = os.environ.get("MEDIA2TEXT_CONFIG", "config.yaml")
        if Path(path).is_file():
            data = yaml.safe_load(Path(path).read_text()) or {}
            _resolve_transcribe_engine_env(data)
            return cls.model_validate(data)
        return cls()

    def ensure_workspace(self) -> Path:
        root = self.workspace.resolve()
        for sub in ("sessions", "creators"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root


def _resolve_transcribe_engine_env(data: dict) -> None:
    """If transcribe.engine names an env var (e.g. TRANSCRIBE_ENGINE), use its value."""
    tc = data.get("transcribe")
    if not isinstance(tc, dict):
        return
    eng = tc.get("engine")
    if isinstance(eng, str):
        env_val = os.environ.get(eng, "").strip()
        if env_val:
            tc["engine"] = env_val
