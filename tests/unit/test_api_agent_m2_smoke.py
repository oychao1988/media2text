"""M2 (#182) integration smoke: H2 restart replay, thread switch, tool persistence."""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from media2text.agent.runtime_provider import LlmCompletion, LlmToolCall, MockChatClient
from media2text.api.app import create_app
from media2text.api.deps import get_cfg, get_db
from media2text.api.services.health import clear_health_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = [pytest.mark.desktop, pytest.mark.agent]


def _seed_creator(workspace, *, sec_uid: str = "sec_m2") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
    )
    conn.close()
    return cid


def _fresh_client(workspace) -> TestClient:
    """New FastAPI TestClient on same workspace — simulates API restart (H2)."""
    clear_health_cache()
    cfg = AppConfig.load()
    app = create_app()

    def override_cfg() -> AppConfig:
        return cfg

    def override_db():
        conn = open_db(cfg)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_cfg] = override_cfg
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _wait_turn_messages(api_client: TestClient, thread_id: str, *, min_count: int = 2) -> list:
    for _ in range(40):
        r = api_client.get(f"/api/agent/threads/{thread_id}/messages")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        if len(msgs) >= min_count:
            return msgs
        time.sleep(0.05)
    r = api_client.get(f"/api/agent/threads/{thread_id}/messages")
    return r.json()["messages"]


def test_h2_messages_survive_api_restart(api_client, workspace, monkeypatch) -> None:
    """H2: persisted thread/messages readable after new API process (same DB)."""
    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient([LlmCompletion(content="after restart")]),
    )

    cid = _seed_creator(workspace)
    r = api_client.post("/api/agent/threads", json={"creatorId": cid, "title": "h2"})
    tid = r.json()["thread"]["id"]
    api_client.post(
        f"/api/agent/threads/{tid}/turn",
        json={"text": "before restart", "sidebarCreatorId": cid},
    )
    msgs_before = _wait_turn_messages(api_client, tid)
    assert any(m["role"] == "user" and m["content"] == "before restart" for m in msgs_before)
    assert any(m["role"] == "assistant" and m["content"] == "after restart" for m in msgs_before)

    api_client.close()
    restarted = _fresh_client(workspace)
    try:
        replay = restarted.get(f"/api/agent/threads/{tid}/messages")
        assert replay.status_code == 200
        rows = replay.json()["messages"]
        assert any(m["role"] == "user" and m["content"] == "before restart" for m in rows)
        assert any(m["role"] == "assistant" and m["content"] == "after restart" for m in rows)
    finally:
        restarted.close()


def test_thread_switch_replay_isolated(api_client, workspace, monkeypatch) -> None:
    """Switch thread: each thread GET messages returns its own history (replay)."""
    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient(
            [
                LlmCompletion(content="reply-a"),
                LlmCompletion(content="reply-b"),
            ]
        ),
    )

    cid = _seed_creator(workspace)
    ta = api_client.post("/api/agent/threads", json={"creatorId": cid, "title": "A"}).json()[
        "thread"
    ]["id"]
    tb = api_client.post("/api/agent/threads", json={"creatorId": cid, "title": "B"}).json()[
        "thread"
    ]["id"]

    api_client.post(
        f"/api/agent/threads/{ta}/turn",
        json={"text": "msg-a", "sidebarCreatorId": cid},
    )
    _wait_turn_messages(api_client, ta)
    api_client.post(
        f"/api/agent/threads/{tb}/turn",
        json={"text": "msg-b", "sidebarCreatorId": cid},
    )
    _wait_turn_messages(api_client, tb)

    ma = api_client.get(f"/api/agent/threads/{ta}/messages").json()["messages"]
    mb = api_client.get(f"/api/agent/threads/{tb}/messages").json()["messages"]
    assert any(m["content"] == "msg-a" for m in ma)
    assert any(m["content"] == "reply-a" for m in ma)
    assert not any(m["content"] == "msg-b" for m in ma)
    assert any(m["content"] == "msg-b" for m in mb)
    assert not any(m["content"] == "msg-a" for m in mb)


def test_tool_result_persisted_and_ws_stream(api_client, workspace, monkeypatch) -> None:
    """Tool turn: WS emits tool.start/result; messages list includes tool role after turn.end."""
    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient(
            [
                LlmCompletion(
                    tool_calls=[
                        LlmToolCall(id="tc1", name="list_creators", arguments="{}"),
                    ]
                ),
                LlmCompletion(content="listed creators"),
            ]
        ),
    )

    cid = _seed_creator(workspace)
    tid = api_client.post("/api/agent/threads", json={"creatorId": cid}).json()["thread"]["id"]
    seen: list[str] = []
    errors: list[Exception] = []

    def read_ws() -> None:
        try:
            with api_client.websocket_connect(f"/api/agent/stream?threadId={tid}") as ws:
                ready = json.loads(ws.receive_text())
                assert ready["type"] == "sidecar.ready"
                deadline = time.time() + 15.0
                while time.time() < deadline:
                    event = json.loads(ws.receive_text())
                    if event.get("type") == "ping":
                        continue
                    seen.append(event["type"])
                    if event["type"] == "turn.end":
                        break
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    reader = threading.Thread(target=read_ws, daemon=True)
    reader.start()
    time.sleep(0.2)

    api_client.post(
        f"/api/agent/threads/{tid}/turn",
        json={"text": "list creators", "sidebarCreatorId": cid},
    )
    reader.join(timeout=16.0)
    assert not errors, errors
    assert "tool.start" in seen or "tool.result" in seen
    assert "turn.end" in seen

    msgs = _wait_turn_messages(api_client, tid, min_count=3)
    roles = {m["role"] for m in msgs}
    assert "tool" in roles
    assert any(m["role"] == "assistant" and m["content"] == "listed creators" for m in msgs)
