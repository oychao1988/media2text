"""Auto-repair fixable doctor checks (Playwright, ffmpeg, optional extras)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.doctor_checks import (
    _playwright_browser_ok,
    _playwright_import_ok,
    build_doctor_report,
)

FIXABLE_CHECKS = frozenset(
    {"ffmpeg", "playwright", "playwright_browser", "streaming_stt_deepgram"}
)
BOOTSTRAP_REQUIRED = frozenset({"ffmpeg", "playwright_browser"})


def _run_cmd(args: list[str], *, timeout: float = 600) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            out = (proc.stdout or proc.stderr or "").strip()
            return True, out or "ok"
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err[:500] or f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {int(timeout)}s"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:500]


def _pip_install(spec: str) -> tuple[bool, str]:
    return _run_cmd(
        [sys.executable, "-m", "pip", "install", spec],
        timeout=300,
    )


def _playwright_install_chromium() -> tuple[bool, str]:
    return _run_cmd(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        timeout=900,
    )


def _try_install_ffmpeg(cfg: AppConfig) -> tuple[bool, str]:
    if shutil.which(cfg.live.ffmpeg_path) or shutil.which("ffmpeg"):
        return True, "already present"
    if sys.platform == "darwin" and shutil.which("brew"):
        return _run_cmd(["brew", "install", "ffmpeg"], timeout=900)
    return False, "请手动安装 ffmpeg（macOS: brew install ffmpeg）"


def _deepgram_installed() -> bool:
    try:
        import deepgram  # noqa: F401

        return True
    except ImportError:
        return False


def repair_environment(cfg: AppConfig, conn) -> dict[str, Any]:
    """Attempt to fix auto-repairable checks; return actions + refreshed doctor report."""
    actions: list[dict[str, Any]] = []

    if not _playwright_import_ok():
        ok, msg = _pip_install("playwright")
        actions.append(
            {"name": "playwright", "action": "pip install playwright", "ok": ok, "message": msg}
        )

    if not _playwright_browser_ok():
        ok, msg = _playwright_install_chromium()
        actions.append(
            {
                "name": "playwright_browser",
                "action": "playwright install chromium",
                "ok": ok,
                "message": msg,
            }
        )

    if not shutil.which(cfg.live.ffmpeg_path):
        ok, msg = _try_install_ffmpeg(cfg)
        actions.append(
            {"name": "ffmpeg", "action": "install ffmpeg", "ok": ok, "message": msg}
        )

    if cfg.live.is_streaming_pipeline() and not _deepgram_installed():
        ok, msg = _pip_install("deepgram-sdk>=4.0")
        actions.append(
            {
                "name": "streaming_stt_deepgram",
                "action": "pip install deepgram-sdk",
                "ok": ok,
                "message": msg,
            }
        )

    report = build_doctor_report(cfg, conn)
    repair_ok = all(c["ok"] for c in report["checks"] if c["name"] in BOOTSTRAP_REQUIRED)
    return {
        "repair_ok": repair_ok,
        "actions": actions,
        **report,
    }


def needs_bootstrap_repair(checks: list[dict]) -> bool:
    by_name = {c["name"]: c for c in checks}
    return any(not by_name.get(name, {}).get("ok") for name in BOOTSTRAP_REQUIRED)
