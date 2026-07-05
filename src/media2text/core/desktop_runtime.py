"""Paths for the Tauri-bundled desktop Python runtime."""

from __future__ import annotations

import os
import shutil
import site
import sys
from pathlib import Path

from media2text.core.config import AppConfig


def runtime_root() -> Path | None:
    raw = os.environ.get("M2T_PROJECT_ROOT", "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def bundled_tool(name: str) -> Path | None:
    root = runtime_root()
    if root is None:
        return None
    candidates = [root / "bin" / name, root / "bin" / f"{name}.bin"]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        if candidate.is_file() and candidate.name.endswith(".bin"):
            target = candidate.with_suffix("")
            try:
                if not target.exists():
                    target.write_bytes(candidate.read_bytes())
                target.chmod(0o755)
                if os.access(target, os.X_OK):
                    return target
            except OSError:
                continue
    return None


def resolve_ffmpeg_path(cfg: AppConfig) -> str | None:
    configured = (cfg.live.ffmpeg_path or "").strip()
    if configured and configured not in {"", "ffmpeg"} and shutil.which(configured):
        return configured
    if os.environ.get("M2T_DESKTOP_MANAGED") == "1":
        bundled = bundled_tool("ffmpeg")
        if bundled:
            return str(bundled)
    if configured and shutil.which(configured):
        return configured
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    bundled = bundled_tool("ffmpeg")
    return str(bundled) if bundled else None


def ensure_ffmpeg_config(cfg: AppConfig) -> None:
    resolved = resolve_ffmpeg_path(cfg)
    if not resolved:
        return
    configured = (cfg.live.ffmpeg_path or "").strip()
    if (
        configured
        and configured not in {"", "ffmpeg"}
        and shutil.which(configured)
    ):
        return
    if os.environ.get("M2T_DESKTOP_MANAGED") == "1":
        bundled = bundled_tool("ffmpeg")
        if bundled and configured != str(bundled):
            cfg.live.ffmpeg_path = str(bundled)
            cfg.save()
            return
    if resolved != cfg.live.ffmpeg_path:
        cfg.live.ffmpeg_path = resolved
        cfg.save()


def pip_install_target_writable() -> bool:
    """Return False when the active venv/site-packages is read-only (e.g. DMG mount)."""
    candidates: list[Path] = []
    try:
        candidates.extend(Path(p) for p in site.getsitepackages())
    except (AttributeError, TypeError):
        pass
    try:
        candidates.append(Path(site.getusersitepackages()))
    except (AttributeError, TypeError):
        pass
    candidates.append(Path(sys.prefix))
    seen: set[Path] = set()
    for root in candidates:
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        probe = root / ".m2t_write_probe"
        try:
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            continue
    return False
