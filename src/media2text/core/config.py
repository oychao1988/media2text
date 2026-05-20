from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DouyinPlatformConfig(BaseModel):
    poll_interval_sec: int = 60
    download_concurrency: int = 3
    max_sync_pages: int = 0


class PlatformsConfig(BaseModel):
    douyin: DouyinPlatformConfig = Field(default_factory=DouyinPlatformConfig)


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


class NotifyEventsConfig(BaseModel):
    live_started: bool = True
    new_aweme: bool = True
    recording_completed: bool = True
    transcribe_completed: bool = True


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
    notify: NotifyConfig = Field(default_factory=NotifyConfig)

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
