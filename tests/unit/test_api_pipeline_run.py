import pytest

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_pipeline_run_queues_task(api_client, workspace) -> None:
    cfg = AppConfig(workspace=workspace)
    conn = open_db(cfg)
    try:
        creator_id = CreatorRepo(conn).add(
            sec_uid="test_sec_pipeline",
            profile_url="https://www.douyin.com/user/test_sec_pipeline",
            platform="douyin",
            display_name="Test",
        )
    finally:
        conn.close()

    r = api_client.post(f"/api/creators/{creator_id}/pipeline/run")
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "queued"
    assert body["job_id"]

    r2 = api_client.post(f"/api/creators/{creator_id}/pipeline/run")
    assert r2.status_code == 409


def test_pipeline_run_unknown_creator(api_client) -> None:
    r = api_client.post("/api/creators/no-such-id/pipeline/run")
    assert r.status_code == 404
