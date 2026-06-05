import os
from pathlib import Path

from media2text.core.playwright_env import (
    default_browsers_path,
    ensure_playwright_browsers_path,
)


def test_default_browsers_path_macos_like(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", "/Users/test")
    assert default_browsers_path() == Path("/Users/test/Library/Caches/ms-playwright")


def test_ensure_replaces_cursor_sandbox_path(monkeypatch, tmp_path):
    sandbox = tmp_path / "cursor-sandbox-cache" / "playwright"
    sandbox.mkdir(parents=True)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(sandbox))
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    expected = tmp_path / "home" / "Library/Caches/ms-playwright"

    resolved = ensure_playwright_browsers_path()

    assert resolved == expected
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(expected)
    assert expected.is_dir()


def test_ensure_keeps_trusted_existing_path(monkeypatch, tmp_path):
    trusted = tmp_path / "custom-playwright"
    trusted.mkdir()
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(trusted))

    resolved = ensure_playwright_browsers_path()

    assert resolved == trusted
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(trusted)


def test_launch_chromium_prefers_channel(monkeypatch):
    calls: list[dict] = []

    class FakeChromium:
        def launch(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("channel") == "chromium":
                return object()
            raise RuntimeError("fallback")

    class FakePlaywright:
        chromium = FakeChromium()

    from media2text.core.playwright_env import launch_chromium

    browser = launch_chromium(FakePlaywright(), headless=True)  # type: ignore[arg-type]
    assert browser is not None
    assert calls[0] == {"headless": True, "channel": "chromium"}
