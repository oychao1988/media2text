#!/usr/bin/env python3
"""Benchmark live HLS compression PoC (LSM-0 / spec S6 gate).

Encodes a local FLV/TS sample with the target HLS + HEVC VideoToolbox params from
docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md §7.

Example:
  source .venv/bin/activate
  python scripts/benchmark_live_compress.py \\
    --sample data/creators/<sec_uid>/live/<timestamp>.flv --json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

S6_SIZE_RATIO_MAX = 0.40
S6_REALTIME_FACTOR_MIN = 1.0

VIDEO_CODECS = ("hevc_videotoolbox", "h264_videotoolbox", "libx264")


def compute_s6_result(*, size_ratio: float, encode_realtime_factor: float) -> dict[str, bool]:
    """Return S6 gate booleans used by run_benchmark and unit tests."""
    s6_size_pass = size_ratio <= S6_SIZE_RATIO_MAX
    s6_realtime_pass = encode_realtime_factor >= S6_REALTIME_FACTOR_MIN
    return {
        "s6_size_pass": s6_size_pass,
        "s6_realtime_pass": s6_realtime_pass,
        "s6_pass": s6_size_pass and s6_realtime_pass,
    }

_CODEC_ARGS: dict[str, list[str]] = {
    "hevc_videotoolbox": ["-c:v", "hevc_videotoolbox"],
    "h264_videotoolbox": ["-c:v", "h264_videotoolbox"],
    "libx264": ["-c:v", "libx264", "-preset", "veryfast"],
}


def _run_checked(cmd: list[str], *, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=text, check=False)


def probe_duration(sample_path: Path, ffprobe: str) -> float:
    proc = _run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(sample_path),
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed for {sample_path}")
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"invalid ffprobe duration for {sample_path}") from exc


def _dir_size_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _sample_cpu_pct(pid: int) -> float | None:
    proc = _run_checked(["ps", "-p", str(pid), "-o", "%cpu="])
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _video_codec_args(video_codec: str) -> list[str]:
    if video_codec not in _CODEC_ARGS:
        raise ValueError(
            f"unsupported video_codec: {video_codec!r}; "
            f"expected one of {', '.join(VIDEO_CODECS)}"
        )
    return _CODEC_ARGS[video_codec]


def run_benchmark(
    sample_path: Path,
    *,
    video_codec: str = "hevc_videotoolbox",
    video_bitrate: str = "2M",
    audio_bitrate: str = "128k",
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
) -> dict[str, object]:
    if platform.system() != "Darwin":
        raise RuntimeError(
            "VideoToolbox PoC requires macOS; non-macOS fallback is out of scope for LSM-0"
        )
    if not sample_path.is_file():
        raise FileNotFoundError(f"sample not found: {sample_path}")

    codec_args = _video_codec_args(video_codec)
    input_bytes = sample_path.stat().st_size
    duration_sec = probe_duration(sample_path, ffprobe_path)

    with tempfile.TemporaryDirectory(prefix="live-compress-bench-") as tmp:
        out_dir = Path(tmp)
        master = out_dir / "master.m3u8"
        cmd = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(sample_path),
            *codec_args,
            "-b:v",
            video_bitrate,
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-f",
            "hls",
            "-hls_time",
            "600",
            "-hls_playlist_type",
            "event",
            str(master),
        ]

        cpu_samples: list[float] = []
        stop_event = threading.Event()

        def _poll_cpu() -> None:
            while not stop_event.is_set():
                if proc.poll() is not None:
                    break
                sample = _sample_cpu_pct(proc.pid)
                if sample is not None:
                    cpu_samples.append(sample)
                time.sleep(0.5)

        start = time.perf_counter()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        poller = threading.Thread(target=_poll_cpu, daemon=True)
        poller.start()
        _, stderr = proc.communicate()
        stop_event.set()
        poller.join(timeout=2)
        elapsed = time.perf_counter() - start

        if proc.returncode != 0:
            detail = (stderr or "").strip()
            raise RuntimeError(detail or f"ffmpeg exited {proc.returncode}")

        output_bytes = _dir_size_bytes(out_dir)
        size_ratio = output_bytes / input_bytes if input_bytes else 0.0
        encode_realtime_factor = duration_sec / elapsed if elapsed > 0 else 0.0
        cpu_pct = sum(cpu_samples) / len(cpu_samples) if cpu_samples else None

        s6 = compute_s6_result(
            size_ratio=size_ratio,
            encode_realtime_factor=encode_realtime_factor,
        )
        return {
            "sample_path": str(sample_path.resolve()),
            "video_codec": video_codec,
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
            "size_ratio": round(size_ratio, 4),
            "duration_sec": round(duration_sec, 2),
            "encode_wall_sec": round(elapsed, 2),
            "encode_realtime_factor": round(encode_realtime_factor, 3),
            "cpu_pct": round(cpu_pct, 1) if cpu_pct is not None else None,
            **s6,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark live HLS compression (VideoToolbox / libx264 + event playlist) "
            "against S6 gates: size_ratio <= 0.40, encode_realtime_factor >= 1.0."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sample",
        type=Path,
        help="Local FLV/TS (or other ffmpeg-readable) live recording sample path",
    )
    parser.add_argument(
        "--video-codec",
        choices=VIDEO_CODECS,
        default="hevc_videotoolbox",
        help="Video encoder for the HLS PoC",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON result to stdout",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg binary path",
    )
    parser.add_argument(
        "--ffprobe",
        default="ffprobe",
        help="ffprobe binary path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.sample is None:
        parser.print_help()
        return 0

    if shutil.which(args.ffmpeg) is None:
        print(f"ffmpeg not found: {args.ffmpeg}", file=sys.stderr)
        return 1
    if shutil.which(args.ffprobe) is None:
        print(f"ffprobe not found: {args.ffprobe}", file=sys.stderr)
        return 1

    try:
        result = run_benchmark(
            args.sample.expanduser().resolve(),
            video_codec=args.video_codec,
            ffmpeg_path=args.ffmpeg,
            ffprobe_path=args.ffprobe,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"sample_path: {result['sample_path']}")
        print(f"video_codec: {result['video_codec']}")
        print(f"size_ratio: {result['size_ratio']} (S6 <= {S6_SIZE_RATIO_MAX})")
        print(
            f"encode_realtime_factor: {result['encode_realtime_factor']} "
            f"(S6 >= {S6_REALTIME_FACTOR_MIN})"
        )
        print(f"cpu_pct: {result['cpu_pct']}")
        print(f"s6_pass: {result['s6_pass']}")

    return 0 if result["s6_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
