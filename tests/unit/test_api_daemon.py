import pytest

pytestmark = pytest.mark.desktop


def test_daemon_endpoints_gone(api_client) -> None:
    r = api_client.get("/api/daemon")
    assert r.status_code == 410
    assert r.json()["detail"]["use"] == "/api/runtime"

    r2 = api_client.get("/api/daemon/logs?tail=2")
    assert r2.status_code == 410

    r3 = api_client.post("/api/daemon/start")
    assert r3.status_code == 410
    assert r3.json()["detail"]["start"] == "/api/runtime/start"

    r4 = api_client.post("/api/daemon/stop")
    assert r4.status_code == 410
