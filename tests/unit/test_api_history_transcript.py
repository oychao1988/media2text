import json

import pytest

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_vod_with_transcript(workspace, api_client):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_api_vod",
        profile_url="https://www.douyin.com/user/sec_api_vod",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_api_vod" / "videos" / "999.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"v")
    mp4.with_suffix(".transcript.json").write_text(
        json.dumps({"text": "vod text", "segments": []}), encoding="utf-8"
    )
    AwemeRepo(conn).upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="999",
            title="VOD title",
            create_time=1_700_000_000,
            media_type="video",
        ),
    )
    conn.execute(
        "UPDATE awemes SET local_path = ?, sync_status = 'downloaded' WHERE aweme_id = ?",
        (str(mp4.resolve()), "999"),
    )
    conn.commit()
    conn.close()
    return cid


def test_history_vod_transcript(api_client, workspace) -> None:
    cid = _seed_vod_with_transcript(workspace, api_client)
    r = api_client.get(f"/api/creators/{cid}/history/vod/999/transcript")
    assert r.status_code == 200
    assert r.json()["text"] == "vod text"


def test_history_vod_transcript_404(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_empty",
        profile_url="https://www.douyin.com/user/sec_empty",
        platform="douyin",
    )
    conn.close()
    r = api_client.get(f"/api/creators/{cid}/history/vod/nope/transcript")
    assert r.status_code == 404


def test_sessions_transcript_404_for_aweme_id(api_client, workspace) -> None:
    """REGRESSION: vod aweme_id must not use /api/sessions/{id}/transcript."""
    _seed_vod_with_transcript(workspace, api_client)
    r = api_client.get("/api/sessions/999/transcript")
    assert r.status_code == 404
