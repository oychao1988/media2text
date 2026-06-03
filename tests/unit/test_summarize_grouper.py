from pathlib import Path

from media2text.core.storage.models import LiveSessionRow
from media2text.core.summarize.grouper import build_suggested_groups


def _row(
    *,
    sid: str,
    started: str,
    ended: str | None,
    path: str,
    room_id: str = "room1",
) -> LiveSessionRow:
    return LiveSessionRow(
        id=sid,
        creator_id="c1",
        room_id=room_id,
        ffmpeg_pid=None,
        started_at=started,
        ended_at=ended,
        local_path=path,
        temp_path=None,
        status="completed",
        error=None,
    )


def test_suggested_group_two_parts_31min_gap(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    p1 = live_dir / "20260601T124448Z.mp4"
    p2 = live_dir / "20260601T130643Z.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    t1 = p1.with_suffix(".transcript.json")
    t2 = p2.with_suffix(".transcript.json")
    t1.write_text('{"segments":[{"start":0,"end":1,"text":"a"}]}', encoding="utf-8")
    t2.write_text('{"segments":[{"start":0,"end":1,"text":"b"}]}', encoding="utf-8")

    day = "2026-06-01"
    rows = [
        _row(
            sid="a",
            started=f"{day}T11:00:00+00:00",
            ended=f"{day}T12:00:00+00:00",
            path=str(p1),
        ),
        _row(
            sid="b",
            started=f"{day}T12:31:00+00:00",
            ended=f"{day}T13:00:00+00:00",
            path=str(p2),
        ),
    ]
    groups = build_suggested_groups(
        creator_id="c1",
        rows=rows,
        workspace=tmp_path,
        merge_gap_minutes=60,
        tz="UTC",
    )
    assert len(groups) == 1
    assert len(groups[0].session_ids) == 2
    assert groups[0].gap_minutes == 31


def test_no_group_when_gap_90min(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    p1 = live_dir / "a.mp4"
    p2 = live_dir / "b.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    p1.with_suffix(".transcript.json").write_text(
        '{"segments":[{"start":0,"end":1,"text":"a"}]}', encoding="utf-8"
    )
    p2.with_suffix(".transcript.json").write_text(
        '{"segments":[{"start":0,"end":1,"text":"b"}]}', encoding="utf-8"
    )

    day = "2026-06-01"
    rows = [
        _row(
            sid="a",
            started=f"{day}T10:00:00+00:00",
            ended=f"{day}T11:00:00+00:00",
            path=str(p1),
        ),
        _row(
            sid="b",
            started=f"{day}T12:30:00+00:00",
            ended=f"{day}T13:00:00+00:00",
            path=str(p2),
        ),
    ]
    groups = build_suggested_groups(
        creator_id="c1",
        rows=rows,
        workspace=tmp_path,
        merge_gap_minutes=60,
        tz="UTC",
    )
    assert groups == []


def test_cross_midnight_group_when_enabled(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    p1 = live_dir / "part1.mp4"
    p2 = live_dir / "part2.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    p1.with_suffix(".transcript.json").write_text(
        '{"segments":[{"start":0,"end":1,"text":"a"}]}', encoding="utf-8"
    )
    p2.with_suffix(".transcript.json").write_text(
        '{"segments":[{"start":0,"end":1,"text":"b"}]}', encoding="utf-8"
    )

    rows = [
        _row(
            sid="a",
            started="2026-06-01T23:00:00+00:00",
            ended="2026-06-01T23:50:00+00:00",
            path=str(p1),
        ),
        _row(
            sid="b",
            started="2026-06-02T00:10:00+00:00",
            ended="2026-06-02T01:00:00+00:00",
            path=str(p2),
        ),
    ]
    off = build_suggested_groups(
        creator_id="c1",
        rows=rows,
        workspace=tmp_path,
        merge_gap_minutes=60,
        tz="UTC",
        merge_cross_midnight=False,
    )
    assert off == []

    on = build_suggested_groups(
        creator_id="c1",
        rows=rows,
        workspace=tmp_path,
        merge_gap_minutes=60,
        tz="UTC",
        merge_cross_midnight=True,
    )
    assert len(on) == 1
    assert len(on[0].session_ids) == 2
    assert on[0].date == "2026-06-01"
    assert on[0].gap_minutes == 20
