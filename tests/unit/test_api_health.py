import pytest

pytestmark = pytest.mark.desktop


def test_health_ok(api_client) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "checks" in body
    names = {c["name"] for c in body["checks"]}
    assert "ffmpeg" in names
    assert "playwright" in names


def test_health_cors_allows_tauri_dev_origin(api_client) -> None:
    r = api_client.get(
        "/api/health",
        headers={"Origin": "http://localhost:1420"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:1420"


def test_doctor_run_refreshes(api_client) -> None:
    r = api_client.post("/api/doctor/run")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "checks" in body
