import pytest

pytestmark = pytest.mark.desktop


def test_get_config(api_client) -> None:
    r = api_client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "autoRecord" in body["config"]


def test_patch_config(api_client, workspace) -> None:
    r = api_client.patch("/api/config", json={"theme": "dark", "notifySound": False})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["config"]["theme"] == "dark"
    assert body["config"]["notifySound"] is False
