import json
import threading
import time

import pytest

from media2text.agent.runtime_provider import LlmCompletion, MockChatClient
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = [pytest.mark.desktop, pytest.mark.agent]


def _seed_creator(workspace, *, sec_uid: str = "sec_ws") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
    )
    conn.close()
    return cid


def test_agent_stream_turn_sequence(api_client, workspace, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.agent.ai_agent.build_openai_client",
        lambda *_a, **_k: MockChatClient([LlmCompletion(content="stream ok")]),
    )
    monkeypatch.setattr(
        "media2text.agent.ai_agent.maybe_auto_title_thread",
        lambda *_a, **_k: None,
    )

    cid = _seed_creator(workspace)
    r = api_client.post("/api/agent/threads", json={"creatorId": cid})
    tid = r.json()["thread"]["id"]
    seen: list[str] = []
    errors: list[Exception] = []

    def read_ws() -> None:
        try:
            with api_client.websocket_connect(f"/api/agent/stream?threadId={tid}") as ws:
                ready = json.loads(ws.receive_text())
                assert ready["type"] == "sidecar.ready"
                deadline = time.time() + 15.0
                while time.time() < deadline:
                    msg = ws.receive_text()
                    event = json.loads(msg)
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
        json={"text": "hello", "sidebarCreatorId": cid},
    )

    reader.join(timeout=16.0)
    assert not errors, errors
    assert "turn.start" in seen
    assert "message.assistant.delta" in seen
    assert "turn.end" in seen


def test_cancel_turn_endpoint(api_client) -> None:
    from media2text.agent.turn_registry import turn_registry

    turn_registry.register(turn_id="turn-cancel-test", thread_id="thread-x")
    cancel = api_client.post("/api/agent/turns/turn-cancel-test/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["cancelled"] is True

    missing = api_client.post("/api/agent/turns/not-a-turn/cancel")
    assert missing.status_code == 404
