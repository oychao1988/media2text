import pytest

from media2text.agent.creator_distill.tavily_client import (
    TavilyClient,
    resolve_tavily_api_key,
)
from media2text.core.env_file import upsert_env_var

pytestmark = pytest.mark.agent


def test_resolve_prefers_dotenv_over_empty_environ(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    env = tmp_path / ".env"
    upsert_env_var("TAVILY_API_KEY", "tvly-test", path=env)
    monkeypatch.setattr(
        "media2text.agent.creator_distill.tavily_client.env_file_path",
        lambda: env,
    )
    assert resolve_tavily_api_key(env_key="TAVILY_API_KEY") == "tvly-test"


def test_resolve_falls_back_to_environ(monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    monkeypatch.setattr(
        "media2text.agent.creator_distill.tavily_client.env_file_path",
        lambda: env,
    )
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-env")
    assert resolve_tavily_api_key(env_key="TAVILY_API_KEY") == "tvly-env"


def test_tavily_search_parses_response(monkeypatch) -> None:
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "answer": "ok",
                "results": [{"title": "t", "url": "https://x.com", "content": "c"}],
            }

    monkeypatch.setattr("httpx.post", lambda *a, **k: FakeResp())
    client = TavilyClient(api_key="tvly-x")
    out = client.search("query", max_results=3)
    assert out.answer == "ok"
    assert len(out.results) == 1
    assert out.results[0].title == "t"


def test_tavily_search_retries_on_429(monkeypatch) -> None:
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError(f"unexpected raise for {self.status_code}")

        def json(self):
            return self._payload

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(429)
        return FakeResp(
            200,
            {"answer": "retry-ok", "results": []},
        )

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr("media2text.agent.creator_distill.tavily_client.time.sleep", lambda _: None)
    client = TavilyClient(api_key="tvly-x")
    out = client.search("query")
    assert out.answer == "retry-ok"
    assert calls["n"] == 2


def test_tavily_search_does_not_retry_401(monkeypatch) -> None:
    class FakeResp:
        status_code = 401

        def raise_for_status(self):
            import httpx

            req = httpx.Request("POST", "https://api.tavily.com/search")
            resp = httpx.Response(401, request=req)
            raise httpx.HTTPStatusError("401", request=req, response=resp)

        def json(self):
            return {}

    monkeypatch.setattr("httpx.post", lambda *a, **k: FakeResp())
    client = TavilyClient(api_key="bad")
    with pytest.raises(Exception):
        client.search("query")
