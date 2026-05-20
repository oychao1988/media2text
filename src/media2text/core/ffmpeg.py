import subprocess
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
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def stop_process(proc: subprocess.Popen, *, timeout: int = 30) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def remux_to_mp4(*, ffmpeg: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(src), "-c", "copy", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError("remux produced empty file")
