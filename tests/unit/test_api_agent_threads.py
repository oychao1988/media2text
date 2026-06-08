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


def test_creator_mismatch_allows_turn(api_client, workspace, monkeypatch) -> None:
    from media2text.agent.runtime_provider import LlmCompletion, MockChatClient

    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient([LlmCompletion(content="mock reply")]),
    )

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
    assert r2.status_code == 200
    assert "turnId" in r2.json()


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


def test_activate_thread_updates_binding(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    r = api_client.post("/api/agent/threads", json={"creatorId": cid, "title": "activate"})
    tid = r.json()["thread"]["id"]
    r2 = api_client.patch(
        f"/api/agent/threads/{tid}/activate",
        json={
            "creatorId": cid,
            "sessionId": "sess-1",
            "sessionKind": "vod",
            "transcriptPath": "creators/x/videos/a.transcript.json",
            "summaryPath": None,
            "contextMode": "transcript",
        },
    )
    assert r2.status_code == 200
    thread = r2.json()["thread"]
    assert thread["contextMode"] == "transcript"
    assert thread["sessionId"] == "sess-1"


def test_activate_thread_attachments_round_trip(api_client, workspace) -> None:
    cid = _seed_creator(workspace)
    r = api_client.post("/api/agent/threads", json={"creatorId": cid, "title": "attach"})
    tid = r.json()["thread"]["id"]
    attachments = [
        {
            "id": "transcript:creators/x/live/a.transcript.json",
            "docType": "transcript",
            "path": "creators/x/live/a.transcript.json",
            "label": "直播",
            "creatorId": cid,
            "creatorName": "博主",
            "sessionKind": "live",
            "itemId": "sess-1",
            "source": "session",
        },
        {
            "id": "summary:creators/x/live/a.summary.md",
            "docType": "summary",
            "path": "creators/x/live/a.summary.md",
            "label": "直播",
            "creatorId": cid,
            "creatorName": "博主",
            "sessionKind": "live",
            "itemId": "sess-1",
            "source": "session",
        },
    ]
    r2 = api_client.patch(
        f"/api/agent/threads/{tid}/activate",
        json={
            "creatorId": cid,
            "sessionId": "sess-1",
            "sessionKind": "live",
            "contextMode": "both",
            "attachments": attachments,
        },
    )
    assert r2.status_code == 200
    thread = r2.json()["thread"]
    assert thread["attachments"] == attachments
    assert thread["transcriptPath"] == "creators/x/live/a.transcript.json"
    assert thread["summaryPath"] == "creators/x/live/a.summary.md"

    r3 = api_client.patch(
        f"/api/agent/threads/{tid}/activate",
        json={"creatorId": cid, "sessionId": "sess-1", "attachments": []},
    )
    assert r3.status_code == 200
    cleared = r3.json()["thread"]
    assert cleared["attachments"] == []
    assert cleared.get("transcriptPath") is None
    assert cleared.get("summaryPath") is None
