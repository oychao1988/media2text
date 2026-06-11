"""Unit tests for scripts/benchmark_live_compress.py (S6 gate + CLI surface)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "benchmark_live_compress.py"


def _load_module():
    name = "benchmark_live_compress"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_compute_s6_result_passes_when_both_gates_met() -> None:
    mod = _load_module()
    result = mod.compute_s6_result(size_ratio=0.35, encode_realtime_factor=1.5)
    assert result == {
        "s6_size_pass": True,
        "s6_realtime_pass": True,
        "s6_pass": True,
    }


def test_compute_s6_result_fails_on_size_only() -> None:
    mod = _load_module()
    result = mod.compute_s6_result(size_ratio=0.9975, encode_realtime_factor=10.0)
    assert result["s6_size_pass"] is False
    assert result["s6_realtime_pass"] is True
    assert result["s6_pass"] is False


def test_compute_s6_result_fails_on_realtime_only() -> None:
    mod = _load_module()
    result = mod.compute_s6_result(size_ratio=0.30, encode_realtime_factor=0.5)
    assert result["s6_size_pass"] is True
    assert result["s6_realtime_pass"] is False
    assert result["s6_pass"] is False


def test_compute_s6_result_boundary_values() -> None:
    mod = _load_module()
    at_boundary = mod.compute_s6_result(
        size_ratio=mod.S6_SIZE_RATIO_MAX,
        encode_realtime_factor=mod.S6_REALTIME_FACTOR_MIN,
    )
    assert at_boundary["s6_pass"] is True


def test_video_codec_args_supported_matrix() -> None:
    mod = _load_module()
    assert mod._video_codec_args("hevc_videotoolbox") == ["-c:v", "hevc_videotoolbox"]
    assert mod._video_codec_args("h264_videotoolbox") == ["-c:v", "h264_videotoolbox"]
    assert mod._video_codec_args("libx264") == ["-c:v", "libx264", "-preset", "veryfast"]


def test_video_codec_args_rejects_unknown() -> None:
    mod = _load_module()
    try:
        mod._video_codec_args("vp9")
    except ValueError as exc:
        assert "vp9" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown codec")


def test_build_parser_video_codec_choices() -> None:
    mod = _load_module()
    parser = mod.build_parser()
    args = parser.parse_args(
        ["--sample", "sample.flv", "--video-codec", "libx264", "--json"]
    )
    assert args.video_codec == "libx264"
    assert args.json is True
