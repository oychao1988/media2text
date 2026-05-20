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


class TranscribeConfig(BaseModel):
    engine: str = "whisper"
    language: str = "zh"
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)


class AppConfig(BaseSettings):
    workspace: Path = Path("./data")
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)

    @classmethod
    def load(cls) -> AppConfig:
        path = os.environ.get("MEDIA2TEXT_CONFIG", "config.yaml")
        if Path(path).is_file():
            data = yaml.safe_load(Path(path).read_text()) or {}
            return cls.model_validate(data)
        return cls()

    def ensure_workspace(self) -> Path:
        root = self.workspace.resolve()
        for sub in ("sessions", "creators"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root
