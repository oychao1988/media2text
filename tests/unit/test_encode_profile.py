from unittest.mock import patch

from media2text.core.config import AppConfig, LiveEncodeConfig
from media2text.core.live.encode_profile import resolve_video_encoder


def test_compress_alias_migrates_to_encode() -> None:
    cfg = AppConfig.model_validate(
        {
            "live": {
                "compress": {"enabled": True, "video_bitrate": "2M"},
            }
        }
    )
    assert cfg.live.encode.mode == "compress"
    assert cfg.live.encode.video_bitrate == "2M"


def test_compress_encoder_alias_migrates_to_video_codec() -> None:
    cfg = AppConfig.model_validate(
        {
            "live": {
                "compress": {"enabled": True, "encoder": "libx264"},
            }
        }
    )
    assert cfg.live.encode.mode == "compress"
    assert cfg.live.encode.video_codec == "libx264"


def test_compress_videotoolbox_encoder_keeps_auto_codec() -> None:
    cfg = AppConfig.model_validate(
        {
            "live": {
                "compress": {"enabled": True, "encoder": "videotoolbox"},
            }
        }
    )
    assert cfg.live.encode.mode == "compress"
    assert cfg.live.encode.video_codec == "auto"


def test_resolve_video_encoder_copy_mode() -> None:
    name, args = resolve_video_encoder(LiveEncodeConfig(mode="copy"))
    assert name == "copy"
    assert args == ["-c", "copy"]


def test_resolve_video_encoder_explicit_codec() -> None:
    cfg = LiveEncodeConfig(
        mode="compress",
        video_codec="h264_videotoolbox",
        video_bitrate="1.5M",
        audio_bitrate="96k",
    )
    name, args = resolve_video_encoder(cfg)
    assert name == "h264_videotoolbox"
    assert "-c:v" in args
    assert "h264_videotoolbox" in args
    assert "1.5M" in args
    assert "96k" in args


@patch("media2text.core.live.encode_profile._detect_best_vt_codec")
def test_resolve_video_encoder_auto_uses_detected_codec(mock_detect) -> None:
    mock_detect.return_value = "hevc_videotoolbox"
    cfg = LiveEncodeConfig(mode="compress", video_codec="auto")
    name, args = resolve_video_encoder(cfg)
    assert name == "hevc_videotoolbox"
    assert "hevc_videotoolbox" in args
    mock_detect.assert_called_once()
