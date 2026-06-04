import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, DesktopChatRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_creator(workspace) -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_chat",
        profile_url="https://www.douyin.com/user/sec_chat",
        platform="douyin",
    )
    conn.close()
    return cid


def test_chat_providers(api_client) -> None:
    r = api_client.get("/api/chat/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["providers"], list)


def test_chat_thread_crud(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    r = api_client.post(
        "/api/chat/threads",
        json={
            "creatorId": cid,
            "title": "test thread",
            "model": "auto",
            "contextMode": "both",
        },
    )
    assert r.status_code == 200
    tid = r.json()["thread"]["id"]

    r = api_client.get("/api/chat/threads", params={"creatorId": cid})
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json()["threads"])

    r = api_client.patch(
        f"/api/chat/threads/{tid}",
        json={"title": "renamed", "model": "gpt-4"},
    )
    assert r.status_code == 200
    assert r.json()["thread"]["title"] == "renamed"

    r = api_client.post(
        f"/api/chat/threads/{tid}/messages",
        json={"role": "user", "content": "hello"},
    )
    assert r.status_code == 200
    assert r.json()["message"]["content"] == "hello"

    r = api_client.get(f"/api/chat/threads/{tid}/messages")
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1

    r = api_client.delete(f"/api/chat/threads/{tid}")
    assert r.status_code == 200
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    assert DesktopChatRepo(conn).get_thread(tid) is None
    conn.close()
