import os
import signal
import subprocess
import time
from pathlib import Path


def record_stream_copy(
    *,
    ffmpeg: str,
    stream_url: str,
    output_path: Path,
) -> subprocess.Popen:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        stream_url,
        "-c",
        "copy",
        "-f",
        "flv",
        str(output_path),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_process(proc: subprocess.Popen, *, timeout: int = 30) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def stop_pid(pid: int, *, timeout: int = 30) -> None:
    """SIGTERM then SIGKILL for a child ffmpeg not tracked in a Popen handle."""
    if pid <= 0:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def remux_to_mp4(*, ffmpeg: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(src), "-c", "copy", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError("remux produced empty file")


def concat_to_flv(*, ffmpeg: str, sources: list[Path], dst: Path) -> None:
    """Merge segment FLV files into one output (stream copy)."""
    valid = [p for p in sources if p.is_file() and p.stat().st_size > 0]
    if not valid:
        raise RuntimeError("concat: no valid segment files")
    if len(valid) == 1:
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ffmpeg, "-y", "-i", str(valid[0]), "-c", "copy", str(dst)]
        subprocess.run(cmd, check=True, capture_output=True)
        if not dst.exists() or dst.stat().st_size == 0:
            raise RuntimeError("concat produced empty file")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    list_file = dst.with_suffix(".concat.txt")
    try:
        lines = [f"file '{p.resolve()}'" for p in valid]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd_copy = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(dst),
        ]
        result = subprocess.run(cmd_copy, capture_output=True)
        if result.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return
        cmd_genpts = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-fflags",
            "+genpts",
            str(dst),
        ]
        subprocess.run(cmd_genpts, check=True, capture_output=True)
        if not dst.exists() or dst.stat().st_size == 0:
            raise RuntimeError("concat produced empty file")
    finally:
        list_file.unlink(missing_ok=True)


def concat_to_mp4(*, ffmpeg: str, sources: list[Path], dst: Path) -> None:
    """Merge segment files into one MP4; copy first, then genpts fallback."""
    valid = [p for p in sources if p.is_file() and p.stat().st_size > 0]
    if not valid:
        raise RuntimeError("concat: no valid segment files")
    if len(valid) == 1:
        remux_to_mp4(ffmpeg=ffmpeg, src=valid[0], dst=dst)
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    list_file = dst.with_suffix(".concat.txt")
    try:
        lines = [f"file '{p.resolve()}'" for p in valid]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd_copy = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(dst),
        ]
        result = subprocess.run(cmd_copy, capture_output=True)
        if result.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return
        cmd_genpts = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-fflags",
            "+genpts",
            str(dst),
        ]
        subprocess.run(cmd_genpts, check=True, capture_output=True)
        if not dst.exists() or dst.stat().st_size == 0:
            raise RuntimeError("concat produced empty file")
    finally:
        list_file.unlink(missing_ok=True)
