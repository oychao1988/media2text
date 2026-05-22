from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger()

_DEFAULT_SOUNDS: dict[str, str] = {
    "Darwin": "/System/Library/Sounds/Glass.aiff",
    "Linux": "/usr/share/sounds/freedesktop/stereo/complete.oga",
}


def default_sound_path() -> Path | None:
    custom = _DEFAULT_SOUNDS.get(platform.system())
    if custom and Path(custom).is_file():
        return Path(custom)
    return None


def play_sound(path: Path | None) -> None:
    sound = path if path and path.is_file() else default_sound_path()
    if not sound:
        log.debug("notify_sound_skipped", reason="no_sound_file")
        return
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(
                ["afplay", str(sound)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif system == "Linux":
            subprocess.Popen(
                ["paplay", str(sound)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif system == "Windows":
            import winsound

            winsound.PlaySound(  # type: ignore[attr-defined]
                str(sound),
                winsound.SND_FILENAME | winsound.SND_ASYNC,  # type: ignore[attr-defined]
            )
        else:
            log.debug("notify_sound_skipped", reason="unsupported_platform", platform=system)
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_sound_failed", path=str(sound), error=str(exc))
