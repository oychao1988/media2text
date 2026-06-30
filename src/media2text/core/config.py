from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings

from media2text.core.errors import ConfigError


class DouyinPlatformConfig(BaseModel):
    poll_interval_sec: int = 60
    live_poll_interval_sec: int = 0
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
    executor_max_parallel: int = 1
    stale_running_sec: int = 3600
    task_max_retries: int = 3
    scheduler_interval_sec: int = 1
    reconciler_enabled: bool = True
    reconciler_log_only: bool = False
    live_worker_max_parallel: int = 1
    live_lane_min_claim_per_tick: int = 1
    probe_tick_budget_sec: int = 0
    probe_parallelism: int = 4
    probe_http_timeout_sec: int = 5
    probe_guard_strict: bool = False


class StreamingSttConfig(BaseModel):
    enabled: bool = True
    engine: str = "deepgram"
    flush_interval_sec: float = 30.0
    reconnect: bool = True
    partial_notify_interval_sec: float = 120.0
    partial_notify_min_finals: int = 3


class LiveMediaConfig(BaseModel):
    format: str = "flv"  # flv | hls
    segment_duration_sec: int = 600


class LiveCompressConfig(BaseModel):
    enabled: bool = False
    encoder: str = "videotoolbox"
    video_bitrate: str = "2M"
    audio_bitrate: str = "128k"


class LiveEncodeConfig(BaseModel):
    mode: str = "copy"  # copy | compress
    video_codec: str = "auto"
    video_bitrate: str = "2M"
    audio_bitrate: str = "128k"


class LiveSegmentUploadConfig(BaseModel):
    enabled: bool = True
    delete_local_after_upload: bool = True


class LiveSegmentPipelineConfig(BaseModel):
    enabled: bool = True
    max_parallel: int = 2
    max_attempts: int = 5
    watch_interval_sec: float = 1.0
    stable_mtime_sec: float = 2.0
    upload: LiveSegmentUploadConfig = Field(default_factory=LiveSegmentUploadConfig)


class LiveConfig(BaseModel):
    pipeline_mode: str = "legacy"  # legacy | streaming
    auto_record: bool = True
    remux_on_complete: bool | None = None
    transcribe_on_complete: bool = False
    streaming_stt: StreamingSttConfig = Field(default_factory=StreamingSttConfig)
    media: LiveMediaConfig = Field(default_factory=LiveMediaConfig)
    encode: LiveEncodeConfig = Field(default_factory=LiveEncodeConfig)
    compress: LiveCompressConfig = Field(default_factory=LiveCompressConfig)
    segment_pipeline: LiveSegmentPipelineConfig = Field(
        default_factory=LiveSegmentPipelineConfig
    )
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
    post_process_stale_running_sec: int = 600
    scan_concurrency: int = 4
    # During active recording, treat profile API offline as inconclusive when ffmpeg
    # is still writing or the room reflow API reports live (Douyin profile often flakes).
    offline_trust_recording_signals: bool = True
    # Consecutive obs polls with profile offline and FLV not growing before ending
    # recording trust (guards zombie ffmpeg after stream ends).
    offline_flv_stall_polls: int = 3

    def effective_pipeline_mode(self) -> str:
        mode = (self.pipeline_mode or "legacy").strip().lower()
        return mode if mode in ("legacy", "streaming") else "legacy"

    def is_streaming_pipeline(self) -> bool:
        return (
            self.effective_pipeline_mode() == "streaming"
            and self.streaming_stt.enabled
        )

    def uses_hls_media(self) -> bool:
        return (self.media.format or "flv").strip().lower() == "hls"

    def snapshot_pipeline_mode(self) -> str:
        """Value stored on live_sessions.pipeline_mode at session create."""
        return "streaming" if self.is_streaming_pipeline() else "legacy"

    def should_remux_on_complete(self) -> bool:
        if self.remux_on_complete is not None:
            return self.remux_on_complete
        return self.effective_pipeline_mode() != "streaming"

    @model_validator(mode="after")
    def _migrate_compress_to_encode(self) -> LiveConfig:
        if self.compress.enabled and self.encode.mode == "copy":
            self.encode.mode = "compress"
            if self.compress.video_bitrate:
                self.encode.video_bitrate = self.compress.video_bitrate
            if self.compress.audio_bitrate:
                self.encode.audio_bitrate = self.compress.audio_bitrate
        enc = (self.compress.encoder or "").strip().lower()
        if enc and self.encode.video_codec == "auto":
            codec_map = {
                "videotoolbox": "auto",
                "vt": "auto",
                "libx264": "libx264",
                "x264": "libx264",
                "h264_videotoolbox": "h264_videotoolbox",
                "hevc_videotoolbox": "hevc_videotoolbox",
                "libx265": "libx265",
            }
            mapped = codec_map.get(enc)
            if mapped:
                self.encode.video_codec = mapped
            elif enc not in ("auto", ""):
                self.encode.video_codec = enc
        return self

    @model_validator(mode="after")
    def _validate_streaming_pipeline(self) -> LiveConfig:
        if self.is_streaming_pipeline() and self.transcribe_on_complete:
            raise ConfigError(
                "live.transcribe_on_complete must be false when pipeline_mode=streaming "
                "(streaming STT replaces post-recording transcribe)"
            )
        return self


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
    default_provider: str | None = None
    default_model: str | None = None
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
    merge_cross_midnight: bool = False
    per_part: bool = True


class SummarizeConfig(BaseModel):
    enabled: bool = False
    engine: str = "openai"
    on_transcribe_complete: bool = False
    default_profile: str = "auto"
    merge_gap_minutes: int = 60
    merge_date_tz: str = "UTC"
    parse_sections: bool = True
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
    transcribe_partial: bool = False
    summarize_completed: bool = True
    upload_completed: bool = True
    upload_failed: bool = True
    upload_skipped: bool = True
    upload_cleanup: bool = True


class AliyunDriveRollingCleanupConfig(BaseModel):
    max_delete_per_round: int = 20
    purge_recycle_bin: bool = True


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


class DesktopChatConfig(BaseModel):
    default_model: str = "auto"
    max_context_chars: int = 24000


class MemoryConfig(BaseModel):
    max_chars: int = 2200
    user_max_chars: int = 1375
    soul_max_chars: int = 4000
    memory_enabled: bool = True
    user_profile_enabled: bool = True
    soul_enabled: bool = True
    nudge_interval: int = 10  # 0 = disable memory review


class SkillsConfig(BaseModel):
    creation_nudge_interval: int = 10
    agent_skills_subdir: str = "skills"


class CuratorConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = 168
    min_idle_hours: int = 2
    backup_keep: int = 5


class CompressionConfig(BaseModel):
    enabled: bool = True
    preflight_ratio: float = 0.5
    auto_ratio: float = 0.85
    protect_last_n: int = 20


class AgentLoopConfig(BaseModel):
    max_turns: int = 25
    review_enabled: bool = True
    review_max_iterations: int = 16


class AuxiliarySlotConfig(BaseModel):
    provider: str = "auto"
    model: str = "auto"
    timeout: int = 300


class AuxiliaryConfig(BaseModel):
    review: AuxiliarySlotConfig = Field(default_factory=AuxiliarySlotConfig)
    curator: AuxiliarySlotConfig = Field(default_factory=AuxiliarySlotConfig)


class TerminalConfig(BaseModel):
    backend: str = "local"
    cwd: str = "./data"
    default_shell: str = "bash"
    timeout_sec: float = 60.0


class SecurityConfig(BaseModel):
    command_approval: str = "prompt"  # prompt | allowlist | off
    allowlist: list[str] = Field(default_factory=list)


class DelegationConfig(BaseModel):
    max_concurrent_children: int = 2
    max_spawn_depth: int = 2
    orchestrator_enabled: bool = False


class LocalScanConfig(BaseModel):
    enabled: bool = True
    include_manifest: bool = True
    max_files: int = 50
    globs: list[str] = Field(
        default_factory=lambda: [
            "live/**/*.summary.md",
            "live/**/*.transcript.md",
            "videos/**/*.summary.md",
            "videos/**/*.transcript.md",
            "dynamics/**/content.md",
        ]
    )
    user_sources_dir: str = ".agent/sources"


class DistillConfig(BaseModel):
    on_creator_add: bool = False
    max_input_chars: int = 120_000
    defer_until_min_chars: int = 2000
    bootstrap_priority: int = 5
    evolve_priority: int = 10
    max_concurrent_jobs: int = 1
    bootstrap_web_research: bool = True
    evolve_web_research: bool = False
    web_research_channels: int = 6
    web_research_max_parallel: int = 2
    web_search_provider: str = "tavily"
    tavily_api_key_env: str = "TAVILY_API_KEY"
    web_search_smoke: bool = True
    tavily_search_depth: str = "basic"
    tavily_include_answer: bool = True
    tavily_extract_top_urls: int = 0
    web_search_timeout_sec: int = 60
    web_search_max_results: int = 5
    web_source_denylist: list[str] = Field(
        default_factory=lambda: [
            "zhihu.com",
            "mp.weixin.qq.com",
            "baike.baidu.com",
        ]
    )
    local_scan: LocalScanConfig = Field(default_factory=LocalScanConfig)
    allow_web_research: bool = False
    nuwa_skill_path: str | None = None
    evolve_on: list[str] = Field(default_factory=lambda: ["summarize_completed"])

    @model_validator(mode="before")
    @classmethod
    def _compat_allow_web_research(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("allow_web_research") is True and "bootstrap_web_research" not in data:
                data = {**data, "bootstrap_web_research": True}
        return data


class DesktopAgentConfig(BaseModel):
    max_tool_output_chars: int = 16000
    session_search_default_limit: int = 8
    llm_timeout_sec: int = 120
    allow_toolsets: list[str] = Field(
        default_factory=lambda: ["m2t-core", "m2t-terminal", "m2t-delegation"]
    )
    distill: DistillConfig = Field(default_factory=DistillConfig)


class DesktopConfig(BaseModel):
    api_port: int = 8765
    theme: str = "light"
    auto_start_monitor: bool = False
    monitor_self_heal: bool = True
    monitor_self_heal_cooldown_sec: int = 120
    monitor_self_heal_max_per_hour: int = 3
    monitor_self_heal_check_every_sec: int = 30
    external_drain_interval_sec: int = 5
    runtime_ws_interval_sec: int = 30
    runtime_http_fallback_sec: int = 60
    runtime_failed_recent_threshold: int = 10
    chat: DesktopChatConfig = Field(default_factory=DesktopChatConfig)
    agent: DesktopAgentConfig = Field(default_factory=DesktopAgentConfig)


class NotifyConfig(BaseModel):
    enabled: bool = False
    sound: bool = True
    sound_path: str = ""
    outbox_only: bool = True
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
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    curator: CuratorConfig = Field(default_factory=CuratorConfig)
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    agent: AgentLoopConfig = Field(default_factory=AgentLoopConfig)
    auxiliary: AuxiliaryConfig = Field(default_factory=AuxiliaryConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    delegation: DelegationConfig = Field(default_factory=DelegationConfig)
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
            _resolve_distill_compat(data)
            return cls.model_validate(data)
        return cls()

    def ensure_workspace(self) -> Path:
        root = self.workspace.resolve()
        for sub in ("sessions", "creators"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root

    def config_path(self) -> Path:
        return Path(os.environ.get("MEDIA2TEXT_CONFIG", "config.yaml"))

    def save(self, path: Path | None = None) -> Path:
        """Persist current settings to config.yaml."""
        target = path or self.config_path()
        data = self.model_dump()
        ws = data.get("workspace")
        if isinstance(ws, Path):
            data["workspace"] = str(ws)
        target.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return target


def _resolve_distill_compat(data: dict) -> None:
    """Map deprecated allow_web_research → bootstrap_web_research when loading YAML."""
    desktop = data.get("desktop")
    if not isinstance(desktop, dict):
        return
    agent = desktop.get("agent")
    if not isinstance(agent, dict):
        return
    distill = agent.get("distill")
    if not isinstance(distill, dict):
        return
    if "bootstrap_web_research" not in distill and distill.get("allow_web_research") is True:
        distill["bootstrap_web_research"] = True


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
