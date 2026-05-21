import json

from media2text.core.archive.indexer import index_all, index_transcript_file
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.db import connect
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo


def _write_transcript(path, *, segments: list[dict] | str) -> None:
    if isinstance(segments, str):
        path.write_text(segments, encoding="utf-8")
    else:
        path.write_text(
            json.dumps({"engine": "test", "model": "m", "text": "x", "segments": segments}),
            encoding="utf-8",
        )


def test_index_transcript_live_idempotent(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAarchive"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    mp4 = live_dir / "20260520T120000Z.mp4"
    mp4.write_bytes(b"\x00")
    transcript = mp4.with_suffix(".transcript.json")
    _write_transcript(
        transcript,
        segments=[
            {"start": 0.0, "end": 1.0, "text": "半导体板块"},
            {"start": 1.0, "end": 2.0, "text": "继续观察"},
        ],
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(live_dir / "x.flv"),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(mp4.resolve()),
        ended=True,
    )

    n1 = index_transcript_file(conn, transcript, ws)
    n2 = index_transcript_file(conn, transcript, ws)
    assert n1 == 2
    assert n2 == 2
    count = conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0]
    assert count == 2
    hit = conn.execute(
        "SELECT COUNT(*) FROM transcript_segments WHERE text LIKE ?",
        ("%半导体%",),
    ).fetchone()[0]
    assert hit >= 1


def test_index_skips_corrupt_json(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAbad"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    mp4 = live_dir / "bad.mp4"
    mp4.write_bytes(b"\x00")
    transcript = mp4.with_suffix(".transcript.json")
    _write_transcript(transcript, segments="{not json")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(live_dir / "x.flv"),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(mp4.resolve()),
        ended=True,
    )

    stats = index_all(conn, ws)
    assert stats.indexed_files == 0
    assert str(transcript.resolve()) in stats.skipped


def test_index_rebuild_vod(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAvod"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    videos = ws / "creators" / sec_uid / "videos"
    videos.mkdir(parents=True)
    mp4 = videos / "7123456789.mp4"
    mp4.write_bytes(b"\x00")
    transcript = mp4.with_suffix(".transcript.json")
    _write_transcript(
        transcript,
        segments=[{"start": 0.0, "end": 1.0, "text": "关键词测试"}],
    )
    AwemeRepo(conn).upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="7123456789",
            title="t",
            create_time=1_700_000_000,
            media_type="video",
        ),
    )
    conn.execute(
        "UPDATE awemes SET local_path = ?, sync_status = 'downloaded' WHERE aweme_id = ?",
        (str(mp4.resolve()), "7123456789"),
    )
    conn.commit()

    stats = index_all(conn, ws, rebuild=True)
    assert stats.indexed_files == 1
    assert stats.indexed_segments == 1
    row = conn.execute(
        "SELECT session_type, session_id FROM transcript_segments LIMIT 1"
    ).fetchone()
    assert row["session_type"] == "vod"
    assert row["session_id"] == "7123456789"
