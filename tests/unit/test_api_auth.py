import pytest

from media2text.api.deps import set_spawn_login

pytestmark = pytest.mark.desktop


@pytest.fixture(autouse=True)
def _stub_auth_spawn():
    set_spawn_login(lambda platform: {"ok": True, "spawned": True, "platform": platform})
    yield
    set_spawn_login(None)


def test_auth_status(api_client) -> None:
    r = api_client.get("/api/auth/status", params={"validate": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "douyin" in body["platforms"]
    douyin = body["platforms"]["douyin"]
    assert "configured" in douyin
    assert "valid" in douyin
    assert "status" in douyin


def test_auth_login_spawned(api_client) -> None:
    r = api_client.post("/api/auth/login/douyin")
    assert r.status_code == 200
    body = r.json()
    assert body["spawned"] is True
    assert body["platform"] == "douyin"


def test_auth_login_invalid_platform(api_client) -> None:
    r = api_client.post("/api/auth/login/twitter")
    assert r.status_code == 400
