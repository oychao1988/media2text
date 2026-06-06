import time

import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, DesktopChatRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_creator(workspace, *, sec_uid: str = "sec_agent") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
    )
    conn.close()
    return cid


def test_create_thread_without_creator(api_client) -> None:
    r = api_client.post("/api/agent/threads", json={"title": "global"})
    assert r.status_code == 200
    thread = r.json()["thread"]
    assert thread["id"]
    assert thread["creator_id"] is None


def test_creator_mismatch_409(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    other = _seed_creator(workspace, sec_uid="sec_agent_other")
    r = api_client.post(
        "/api/agent/threads",
        json={"creatorId": cid, "title": "creator thread"},
    )
    tid = r.json()["thread"]["id"]

    r2 = api_client.post(
        f"/api/agent/threads/{tid}/turn",
        json={"text": "hi", "sidebarCreatorId": other},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "creator_mismatch"


def test_global_thread_skips_mismatch(api_client, monkeypatch) -> None:
    from media2text.agent.runtime_provider import LlmCompletion, MockChatClient

    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient([LlmCompletion(content="mock reply")]),
    )

    r = api_client.post("/api/agent/threads", json={"title": "global"})
    tid = r.json()["thread"]["id"]
    r2 = api_client.post(
        f"/api/agent/threads/{tid}/turn",
        json={"text": "hi", "sidebarCreatorId": "any-creator"},
    )
    assert r2.status_code == 200
    assert "turnId" in r2.json()


def test_turn_async_persists_messages(api_client, workspace, monkeypatch) -> None:
    from media2text.agent.runtime_provider import LlmCompletion, MockChatClient

    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient([LlmCompletion(content="mock reply")]),
    )

    cid = _seed_creator(workspace)
    r = api_client.post("/api/agent/threads", json={"creatorId": cid})
    tid = r.json()["thread"]["id"]
    r2 = api_client.post(
        f"/api/agent/threads/{tid}/turn",
        json={"text": "async", "sidebarCreatorId": cid},
    )
    assert r2.status_code == 200
    turn_id = r2.json()["turnId"]
    assert turn_id

    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    chat = DesktopChatRepo(conn)
    for _ in range(20):
        msgs = chat.list_messages(tid)
        if len(msgs) >= 2:
            break
        time.sleep(0.05)
    msgs = chat.list_messages(tid)
    conn.close()
    assert any(m.content == "mock reply" for m in msgs)
