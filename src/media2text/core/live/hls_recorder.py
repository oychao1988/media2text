from __future__ import annotations

import subprocess
from pathlib import Path

from media2text.core.config import LiveCompressConfig
from media2text.core.ffmpeg import stop_process


def part_rel_path(part_index: int) -> str:
    return f"parts/seg-{part_index:05d}.m4s"


def build_hls_recorder_args(
    *,
    ffmpeg: str,
    stream_url: str,
    session_dir: Path,
    segment_sec: int,
    compress_cfg: LiveCompressConfig,
    start_segment_number: int = 1,
) -> list[str]:
    session_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    master = session_dir / "master.m3u8"
    segment_pattern = str(parts_dir / "seg-%05d.m4s")

    cmd: list[str] = [
        ffmpeg,
        "-y",
        "-i",
        stream_url,
    ]
    if compress_cfg.enabled:
        cmd.extend(
            [
                "-c:v",
                "hevc_videotoolbox",
                "-b:v",
                compress_cfg.video_bitrate,
                "-c:a",
                "aac",
                "-b:a",
                compress_cfg.audio_bitrate,
            ]
        )
    else:
        cmd.extend(["-c", "copy"])

    cmd.extend(
        [
            "-f",
            "hls",
            "-hls_time",
            str(segment_sec),
            "-hls_playlist_type",
            "event",
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            "init.mp4",
            "-hls_segment_filename",
            segment_pattern,
            "-start_number",
            str(start_segment_number),
            "-hls_flags",
            "append_list+omit_endlist",
            str(master),
        ]
    )
    return cmd


def spawn_hls_recorder(
    *,
    ffmpeg: str,
    stream_url: str,
    session_dir: Path,
    segment_sec: int,
    compress_cfg: LiveCompressConfig,
    start_segment_number: int = 1,
) -> subprocess.Popen:
    cmd = build_hls_recorder_args(
        ffmpeg=ffmpeg,
        stream_url=stream_url,
        session_dir=session_dir,
        segment_sec=segment_sec,
        compress_cfg=compress_cfg,
        start_segment_number=start_segment_number,
    )
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def stop_hls_recorder(proc: subprocess.Popen, *, timeout: int = 30) -> None:
    stop_process(proc, timeout=timeout)


def append_discontinuity_to_playlist(session_dir: Path) -> None:
    """Append one DISCONTINUITY marker per reconnect (D13; may repeat)."""
    master = session_dir / "master.m3u8"
    if not master.is_file():
        return
    lines = master.read_text(encoding="utf-8").rstrip().splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        lines.insert(0, "#EXTM3U")
    marker = "#EXT-X-DISCONTINUITY"
    if lines and lines[-1].strip() == "#EXT-X-ENDLIST":
        lines.insert(-1, marker)
    else:
        lines.append(marker)
    master.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize_hls_endlist(session_dir: Path) -> None:
    master = session_dir / "master.m3u8"
    if not master.is_file():
        return
    text = master.read_text(encoding="utf-8")
    if "#EXT-X-ENDLIST" in text:
        return
    lines = text.rstrip().splitlines()
    lines.append("#EXT-X-ENDLIST")
    master.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rotate_hls_after_reconnect(
    *,
    conn,
    session_id: str,
    session_dir: Path,
    next_index: int,
    discontinuity_seq: int,
) -> None:
    del conn, session_id, next_index, discontinuity_seq  # spawn path owns DB upsert
    append_discontinuity_to_playlist(session_dir)
