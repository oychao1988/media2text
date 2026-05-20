from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_NAME = "douyin.json"


def session_path(workspace: Path) -> Path:
    return workspace / "sessions" / SESSION_NAME


def login_interactive(workspace: Path, *, headless: bool = False) -> Path:
    path = session_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
        input("Press Enter after you have logged in to Douyin...")
        context.storage_state(path=str(path))
        browser.close()
    path.chmod(0o600)
    return path


def session_exists(workspace: Path) -> bool:
    return session_path(workspace).is_file()
