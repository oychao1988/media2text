import pytest

from media2text.core.config import AppConfig
from media2text.core.doctor_repair import (
    needs_bootstrap_repair,
    repair_environment,
)
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo

pytestmark = pytest.mark.desktop


def test_needs_bootstrap_repair_when_playwright_browser_missing() -> None:
    checks = [
        {"name": "ffmpeg", "ok": True},
        {"name": "playwright_browser", "ok": False},
    ]
    assert needs_bootstrap_repair(checks) is True


def test_needs_bootstrap_repair_false_when_ready() -> None:
    checks = [
        {"name": "ffmpeg", "ok": True},
        {"name": "playwright_browser", "ok": True},
    ]
    assert needs_bootstrap_repair(checks) is False


def test_repair_environment_calls_playwright_install(monkeypatch, tmp_path) -> None:
    cfg = AppConfig(workspace=str(tmp_path / "data"))
    conn = connect(tmp_path / "data" / "media2text.db")
    CreatorRepo(conn).add(
        sec_uid="sec_repair",
        profile_url="https://www.douyin.com/user/sec_repair",
        platform="douyin",
    )

    calls: list[list[str]] = []
    browser_ok = {"value": False}

    monkeypatch.setattr(
        "media2text.core.doctor_repair._playwright_import_ok",
        lambda: True,
    )

    def browser_ok_fn() -> bool:
        return browser_ok["value"]

    monkeypatch.setattr(
        "media2text.core.doctor_repair._playwright_browser_ok",
        browser_ok_fn,
    )
    monkeypatch.setattr(
        "media2text.core.doctor_repair.shutil.which",
        lambda _: "/usr/bin/ffmpeg",
    )

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if "playwright" in args and "install" in args:
            browser_ok["value"] = True
        return True, "ok"

    monkeypatch.setattr("media2text.core.doctor_repair._run_cmd", fake_run)

    result = repair_environment(cfg, conn)
    assert result["repair_ok"] is True
    assert any(a["name"] == "playwright_browser" for a in result["actions"])
    assert any("playwright" in " ".join(c) and "install" in " ".join(c) for c in calls)
    conn.close()


def test_doctor_repair_api(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.api.routes.health.repair_environment",
        lambda cfg, conn: {
            "repair_ok": True,
            "actions": [{"name": "playwright_browser", "ok": True, "message": "ok"}],
            "ok": True,
            "checks": [
                {"name": "ffmpeg", "ok": True},
                {"name": "playwright_browser", "ok": True},
            ],
            "compliance_accepted": True,
            "index_stale": False,
            "monitor_lock_pid": None,
        },
    )
    r = api_client.post("/api/doctor/repair")
    assert r.status_code == 200
    body = r.json()
    assert body["repair_ok"] is True
    assert body["actions"]
