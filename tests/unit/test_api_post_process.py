import pytest

pytestmark = pytest.mark.desktop


def test_post_process_run_empty(api_client) -> None:
    r = api_client.post("/api/post-process/run", json={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["command"] == "post-process run"
    assert body["processed"] == 0


def test_post_process_retry_not_found(api_client) -> None:
    r = api_client.post("/api/post-process/retry/missing-job")
    assert r.status_code == 404
