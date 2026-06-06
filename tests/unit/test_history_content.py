import json

import pytest
from fastapi import HTTPException

from media2text.api.services.history_content import (
    read_history_summary,
    read_history_transcript,
    resolve_history_media_path,
)
from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_resolve_live_media_path(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_hc",
        profile_url="https://www.douyin.com/user/sec_hc",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_hc" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T100000Z.flv"
    flv.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(creator_id=cid, room_id="r", temp_path=str(flv))

    media = resolve_history_media_path(conn, workspace=workspace, creator_id=cid, kind="live", item_id=sid)
    conn.close()
    assert media is not None
    assert media.name.endswith(".flv")


def test_read_history_transcript_vod(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_vod",
        profile_url="https://www.douyin.com/user/sec_vod",
        platform="douyin",
    )
    vid_dir = workspace / "creators" / "sec_vod" / "videos"
    vid_dir.mkdir(parents=True)
    mp4 = vid_dir / "7123456789.mp4"
    mp4.write_bytes(b"mp4")
    transcript = mp4.with_suffix(".transcript.json")
    transcript.write_text(json.dumps({"text": "hello", "segments": []}), encoding="utf-8")
    AwemeRepo(conn).upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="7123456789",
            title="测试作品",
            create_time=1_700_000_000,
            media_type="video",
        ),
    )
    conn.execute(
        "UPDATE awemes SET local_path = ?, sync_status = 'downloaded' WHERE aweme_id = ?",
        (str(mp4.resolve()), "7123456789"),
    )
    conn.commit()

    payload = read_history_transcript(
        conn, workspace=workspace, creator_id=cid, kind="vod", item_id="7123456789"
    )
    conn.close()
    assert payload["text"] == "hello"
    assert payload["partial"] is False


def test_read_history_transcript_not_found(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_nf",
        profile_url="https://www.douyin.com/user/sec_nf",
        platform="douyin",
    )
    with pytest.raises(HTTPException) as exc:
        read_history_transcript(
            conn, workspace=workspace, creator_id=cid, kind="vod", item_id="missing"
        )
    conn.close()
    assert exc.value.status_code == 404
