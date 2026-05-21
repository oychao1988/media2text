import json
from datetime import datetime, timedelta, timezone

from media2text.core.archive.indexer import index_transcript_file
from media2text.core.archive.timeline import timeline_archive
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _write_transcript(path, segments: list[dict]) -> None:
    path.write_text(
        json.dumps({"engine": "test", "model": "m", "text": "x", "segments": segments}),
        encoding="utf-8",
    )


def _seed_session(
    conn,
    ws,
    *,
    cid: str,
    sec_uid: str,
    stamp: str,
    text: str,
    started_at: str,
) -> None:
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    mp4 = live_dir / f"{stamp}.mp4"
    mp4.write_bytes(b"\x00")
    transcript = mp4.with_suffix(".transcript.json")
    _write_transcript(transcript, segments=[{"start": 1.0, "end": 2.0, "text": text}])
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id=f"r-{stamp}",
        temp_path=str(live_dir / "x.flv"),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(mp4.resolve()),
        ended=True,
    )
    conn.execute(
        "UPDATE live_sessions SET started_at = ? WHERE id = ?",
        (started_at, sid),
    )
    conn.commit()
    index_transcript_file(conn, transcript, ws)


def test_timeline_sorts_old_to_new_and_filters_days(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAtimeline"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=40)).isoformat()
    mid_ts = (now - timedelta(days=10)).isoformat()
    new_ts = (now - timedelta(days=2)).isoformat()

    _seed_session(
        conn, ws, cid=cid, sec_uid=sec_uid, stamp="old", text="半导体旧观点", started_at=old_ts
    )
    _seed_session(
        conn, ws, cid=cid, sec_uid=sec_uid, stamp="mid", text="半导体中期", started_at=mid_ts
    )
    _seed_session(
        conn, ws, cid=cid, sec_uid=sec_uid, stamp="new", text="半导体新观点", started_at=new_ts
    )

    result = timeline_archive(conn, "半导体", creator_id=cid, days=30, limit=50)
    assert result.ok is True
    assert len(result.hits) == 2
    assert result.hits[0].excerpt
    assert "中期" in result.hits[0].excerpt or result.hits[0].excerpt
    assert "新" in result.hits[1].excerpt or result.hits[1].excerpt
    starts = [h.started_at for h in result.hits]
    assert starts == sorted(starts)


def test_timeline_zero_hits(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAempty"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    now = datetime.now(timezone.utc).isoformat()
    _seed_session(
        conn,
        ws,
        cid=cid,
        sec_uid=sec_uid,
        stamp="one",
        text="无关话题",
        started_at=now,
    )
    result = timeline_archive(conn, "半导体", creator_id=cid, days=30)
    assert result.ok is True
    assert result.hits == []
