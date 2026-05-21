import json

from media2text.core.archive.indexer import index_transcript_file
from media2text.core.archive.search import search_archive
from media2text.core.compliance import accept_compliance
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _write_transcript(path, segments: list[dict]) -> None:
    path.write_text(
        json.dumps({"engine": "test", "model": "m", "text": "x", "segments": segments}),
        encoding="utf-8",
    )


def _seed_live_index(tmp_path) -> tuple:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    sec_uid = "MS4wLjABAAAAsearch"
    cid = CreatorRepo(conn).add(sec_uid=sec_uid, profile_url="https://example.com/u")
    live_dir = ws / "creators" / sec_uid / "live"
    live_dir.mkdir(parents=True)
    mp4 = live_dir / "20260520T120000Z.mp4"
    mp4.write_bytes(b"\x00")
    transcript = mp4.with_suffix(".transcript.json")
    _write_transcript(
        transcript,
        segments=[
            {"start": 10.0, "end": 12.0, "text": "半导体板块走强"},
            {"start": 12.0, "end": 14.0, "text": "继续观察量能"},
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
    index_transcript_file(conn, transcript, ws)
    return conn, cid, ws


def test_search_returns_hits_with_e1_fields(tmp_path) -> None:
    conn, cid, _ws = _seed_live_index(tmp_path)
    accept_compliance(tmp_path / "data")
    result = search_archive(conn, "半导体", creator_id=cid, limit=10)
    assert result.ok is True
    assert result.indexed is True
    assert len(result.hits) >= 1
    hit = result.hits[0]
    assert hit.segment_id > 0
    assert hit.offset_sec == 10.0
    assert hit.start_sec == 10.0
    assert hit.session_type == "live"
    assert hit.creator_id == cid
    assert hit.sec_uid
    assert "半导体" in hit.excerpt or hit.excerpt
    assert hit.transcript_path.endswith(".transcript.json")
    assert hit.open_path.endswith(".mp4")


def test_search_not_indexed(tmp_path) -> None:
    ws = tmp_path / "data"
    conn = connect(ws / "media2text.db")
    result = search_archive(conn, "半导体")
    assert result.ok is False
    assert result.indexed is False
    assert "archive index" in (result.error or "")


def test_search_invalid_syntax(tmp_path) -> None:
    conn, _cid, _ws = _seed_live_index(tmp_path)
    result = search_archive(conn, 'foo"bar')
    assert result.ok is False
    assert result.error == "invalid search syntax"
