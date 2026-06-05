import pytest

pytestmark = pytest.mark.desktop


def test_monitor_task_retry_not_found(api_client) -> None:
    r = api_client.post("/api/monitor-tasks/retry/missing-task")
    assert r.status_code == 404
