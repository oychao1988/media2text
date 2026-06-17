"""Normalize Playwright browser cache path for CLI, serve sidecar, and doctor."""

from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright

# monitor watch runs sync_catalog + prepare_live_recording concurrently; serialize
# Chromium launches so stream resolve does not fail with launch_failed.
# Increased from 1→2 in 2026-06-10 to prevent executor deadlock when one task hangs.
_PLAYWRIGHT_EXCLUSIVE = threading.Semaphore(2)
# Timeout for acquiring the Playwright slot — tasks that wait longer fail fast
# so the pool stays available for live-critical tasks.
_PLAYWRIGHT_ACQUIRE_TIMEOUT = 30.0
_PLAYWRIGHT_PROBE_ACQUIRE_TIMEOUT = 90.0


@contextmanager
def playwright_exclusive(timeout: float | None = None) -> Iterator[None]:
    if timeout is None:
        from media2text.core.live.probe_guard import ProbeExecutionGuard

        timeout = (
            _PLAYWRIGHT_PROBE_ACQUIRE_TIMEOUT
            if ProbeExecutionGuard.is_active()
            else _PLAYWRIGHT_ACQUIRE_TIMEOUT
        )
    acquired = _PLAYWRIGHT_EXCLUSIVE.acquire(blocking=True, timeout=timeout)
    if not acquired:
        raise TimeoutError(
            f"failed to acquire Playwright exclusive lock within {timeout}s"
        )
    try:
        yield
    finally:
        _PLAYWRIGHT_EXCLUSIVE.release()


def default_browsers_path() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Caches/ms-playwright"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return Path(local) / "ms-playwright"
        return home / "AppData/Local/ms-playwright"
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    if xdg:
        return Path(xdg) / "ms-playwright"
    return home / ".cache/ms-playwright"


def _is_untrusted_browsers_path(path: str) -> bool:
    lowered = path.lower()
    return "cursor-sandbox-cache" in lowered or "/tmp/cursor-" in lowered


def ensure_playwright_browsers_path() -> Path:
    """Point Playwright at the user cache unless a trusted path is already set."""
    current = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if current and not _is_untrusted_browsers_path(current):
        return Path(current)
    resolved = default_browsers_path()
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(resolved)
    return resolved


@contextmanager
def managed_playwright() -> Iterator[Playwright]:
    """Enter sync_playwright after fixing PLAYWRIGHT_BROWSERS_PATH.

    Playwright resolves browser binaries when the driver starts; calling
    ensure_playwright_browsers_path() only inside launch_chromium() is too late.
    """
    from playwright.sync_api import sync_playwright

    ensure_playwright_browsers_path()
    with sync_playwright() as playwright:
        yield playwright


def launch_chromium(playwright: Playwright, *, headless: bool = True) -> Browser:
    """Launch Chromium for automation.

    Headless mode prefers the full Chrome-for-Testing binary (``channel='chromium'``)
    instead of Playwright's separate ``chromium_headless_shell`` build, which can
    SIGSEGV on some macOS setups.
    """
    ensure_playwright_browsers_path()
    if headless:
        for kwargs in (
            {"headless": True, "channel": "chromium"},
            {"headless": True},
        ):
            try:
                return playwright.chromium.launch(**kwargs)  # type: ignore[arg-type]
            except Exception:
                continue
        raise RuntimeError("playwright_chromium_launch_failed")
    return playwright.chromium.launch(headless=False)


def smoke_launch_chromium() -> tuple[bool, str | None]:
    """Return (ok, hint) after a real headless launch attempt."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "pip install playwright"
    try:
        ensure_playwright_browsers_path()
        with sync_playwright() as p:
            browser = launch_chromium(p, headless=True)
            browser.close()
        return True, None
    except Exception as exc:
        return False, str(exc)
