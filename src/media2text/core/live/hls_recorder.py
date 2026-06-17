from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from media2text.core.config import LiveEncodeConfig
from media2text.core.ffmpeg import stop_process
from media2text.core.live.encode_profile import resolve_video_encoder

HLS_FFMPEG_LOG = "ffmpeg-hls.log"


def read_hls_ffmpeg_log_tail(session_dir: Path, *, max_bytes: int = 500) -> str:
    log_path = session_dir / HLS_FFMPEG_LOG
    if not log_path.is_file():
        return ""
    return log_path.read_bytes()[-max_bytes:].decode(errors="replace")


def part_rel_path(part_index: int) -> str:
    return f"parts/seg-{part_index:05d}.m4s"


def build_hls_recorder_args(
    *,
    ffmpeg: str,
    stream_url: str,
    session_dir: Path,
    segment_sec: int,
    encode_cfg: LiveEncodeConfig,
    start_segment_number: int = 1,
) -> list[str]:
    session_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    master = session_dir / "master.m3u8"
    segment_pattern = str(parts_dir / "seg-%05d.m4s")

    cmd: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
        "-y",
        "-i",
        stream_url,
    ]
    _, encode_args = resolve_video_encoder(encode_cfg, ffmpeg=ffmpeg)
    cmd.extend(encode_args)

    cmd.extend(
        [
            "-f",
            "hls",
            "-hls_base_url",
            "parts/",
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
    encode_cfg: LiveEncodeConfig,
    start_segment_number: int = 1,
) -> subprocess.Popen:
    cmd = build_hls_recorder_args(
        ffmpeg=ffmpeg,
        stream_url=stream_url,
        session_dir=session_dir,
        segment_sec=segment_sec,
        encode_cfg=encode_cfg,
        start_segment_number=start_segment_number,
    )
    log_path = session_dir / HLS_FFMPEG_LOG
    log_handle = open(log_path, "ab")  # noqa: SIM115
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_handle,
    )


def stop_hls_recorder(proc: subprocess.Popen, *, timeout: int = 30) -> None:
    stop_process(proc, timeout=timeout)
    stderr = proc.stderr
    if stderr is not None and hasattr(stderr, "close"):
        try:
            stderr.close()
        except OSError:
            pass


def archive_hls_init(session_dir: Path, *, discontinuity_seq: int) -> Path | None:
    """Preserve init.mp4 before reconnect overwrites it (Safari needs matching init per era)."""
    init = session_dir / "init.mp4"
    if not init.is_file() or init.stat().st_size <= 0:
        return None
    dest = session_dir / f"init-{discontinuity_seq}.mp4"
    if dest.is_file():
        return dest
    shutil.copy2(init, dest)
    return dest


def restore_hls_init_if_empty(session_dir: Path) -> bool:
    """Copy the newest archived init when reconnect left init.mp4 empty."""
    init = session_dir / "init.mp4"
    if init.is_file() and init.stat().st_size > 0:
        return False
    archives = sorted(session_dir.glob("init-*.mp4"), reverse=True)
    for arc in archives:
        if arc.is_file() and arc.stat().st_size > 0:
            shutil.copy2(arc, init)
            return True
    return False


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
    del conn, session_id, next_index  # spawn path owns DB upsert
    if discontinuity_seq > 0:
        archive_hls_init(session_dir, discontinuity_seq=discontinuity_seq)
    append_discontinuity_to_playlist(session_dir)


_EXTINF_RE = re.compile(r"#EXTINF:([\d.]+(?:,.*)?)")


def parse_part_duration_sec(session_dir: Path, part_index: int) -> float | None:
    """Sum #EXTINF durations for segments referencing parts/seg-{index}.m4s."""
    master = session_dir / "master.m3u8"
    if not master.is_file():
        return None
    target = part_rel_path(part_index)
    alt = f"seg-{part_index:05d}.m4s"
    total = 0.0
    pending: float | None = None
    for line in master.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#EXT-X-DISCONTINUITY"):
            continue
        m = _EXTINF_RE.match(stripped)
        if m:
            pending = float(m.group(1).split(",")[0])
            continue
        if pending is not None and not stripped.startswith("#"):
            if stripped == target or stripped.endswith(alt):
                total += pending
            pending = None
    return total if total > 0 else None


def mark_closed_with_duration(
    repo,
    session_id: str,
    part_index: int,
    session_dir: Path,
    *,
    bytes: int | None = None,
) -> None:
    duration_sec = parse_part_duration_sec(session_dir, part_index)
    repo.mark_closed(
        session_id,
        part_index,
        bytes=bytes,
        duration_sec=duration_sec,
    )
