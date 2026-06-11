from __future__ import annotations

import shutil
import subprocess

from media2text.core.config import LiveEncodeConfig

_VT_CODEC_CHAIN = ("hevc_videotoolbox", "h264_videotoolbox", "libx264")


def _ffmpeg_encoders(ffmpeg: str) -> str:
    if not shutil.which(ffmpeg):
        return ""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _encoder_available(ffmpeg: str, encoder: str) -> bool:
    return encoder in _ffmpeg_encoders(ffmpeg)


def _detect_best_vt_codec(ffmpeg: str = "ffmpeg") -> str:
    for codec in _VT_CODEC_CHAIN:
        if _encoder_available(ffmpeg, codec):
            return codec
    return "libx264"


def resolve_video_encoder(
    cfg: LiveEncodeConfig,
    *,
    ffmpeg: str = "ffmpeg",
) -> tuple[str, list[str]]:
    """Return (profile_name, ffmpeg args) for HLS video encoding."""
    if cfg.mode != "compress":
        return "copy", ["-c", "copy"]

    codec = (cfg.video_codec or "auto").strip().lower()
    if codec == "auto":
        codec = _detect_best_vt_codec(ffmpeg)

    video_args: list[str] = ["-c:v", codec, "-b:v", cfg.video_bitrate]
    if codec == "libx264":
        video_args.extend(["-preset", "veryfast"])

    audio_args = ["-c:a", "aac", "-b:a", cfg.audio_bitrate]
    return codec, video_args + audio_args
