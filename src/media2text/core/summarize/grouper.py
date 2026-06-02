from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from media2text.core.storage.models import LiveSessionRow
from media2text.core.summarize.reader import transcript_path_for_media


@dataclass
class SuggestedGroup:
    date: str
    creator_id: str
    session_ids: list[str]
    media_paths: list[str]
    gap_minutes: int | None
    room_id: str | None
    group_index: int
    merge_command: str

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "creator_id": self.creator_id,
            "session_ids": self.session_ids,
            "media_paths": self.media_paths,
            "gap_minutes": self.gap_minutes,
            "room_id": self.room_id,
            "group_index": self.group_index,
            "merge_command": self.merge_command,
        }


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def session_end_ts(row: LiveSessionRow) -> datetime | None:
    return _parse_ts(row.ended_at) or _parse_ts(row.started_at)


def session_start_ts(row: LiveSessionRow) -> datetime | None:
    return _parse_ts(row.started_at)


def _calendar_date(ts: datetime, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    local = ts.astimezone(tz)
    return local.date().isoformat()


def _gap_minutes(a_end: datetime, b_start: datetime) -> float:
    return (b_start - a_end).total_seconds() / 60.0


def _has_transcript(row: LiveSessionRow) -> bool:
    if not row.local_path:
        return False
    return transcript_path_for_media(Path(row.local_path)).is_file()


def build_suggested_groups(
    *,
    creator_id: str,
    rows: list[LiveSessionRow],
    workspace: Path,
    merge_gap_minutes: int,
    tz: str,
) -> list[SuggestedGroup]:
    eligible = [
        r
        for r in rows
        if r.status == "completed" and r.local_path and _has_transcript(r)
    ]
    eligible.sort(key=lambda r: session_start_ts(r) or datetime.min.replace(tzinfo=ZoneInfo("UTC")))

    by_date: dict[str, list[LiveSessionRow]] = {}
    for row in eligible:
        start = session_start_ts(row)
        if not start:
            continue
        day = _calendar_date(start, tz)
        by_date.setdefault(day, []).append(row)

    groups: list[SuggestedGroup] = []
    group_index = 0

    for day in sorted(by_date.keys()):
        day_rows = by_date[day]
        if len(day_rows) < 2:
            continue

        chain: list[LiveSessionRow] = [day_rows[0]]
        max_gap: float | None = None

        for nxt in day_rows[1:]:
            prev = chain[-1]
            prev_end = session_end_ts(prev)
            nxt_start = session_start_ts(nxt)
            if not prev_end or not nxt_start:
                if len(chain) >= 2:
                    groups.append(
                        _make_group(
                            creator_id=creator_id,
                            day=day,
                            chain=chain,
                            group_index=group_index,
                            max_gap=max_gap,
                        )
                    )
                    group_index += 1
                chain = [nxt]
                max_gap = None
                continue

            gap = _gap_minutes(prev_end, nxt_start)
            same_room = (
                prev.room_id
                and nxt.room_id
                and prev.room_id == nxt.room_id
            )
            if gap <= merge_gap_minutes and (same_room or not prev.room_id or not nxt.room_id):
                max_gap = gap if max_gap is None else max(max_gap, gap)
                chain.append(nxt)
            else:
                if len(chain) >= 2:
                    groups.append(
                        _make_group(
                            creator_id=creator_id,
                            day=day,
                            chain=chain,
                            group_index=group_index,
                            max_gap=max_gap,
                        )
                    )
                    group_index += 1
                chain = [nxt]
                max_gap = None

        if len(chain) >= 2:
            groups.append(
                _make_group(
                    creator_id=creator_id,
                    day=day,
                    chain=chain,
                    group_index=group_index,
                    max_gap=max_gap,
                )
            )
            group_index += 1

    return groups


def _make_group(
    *,
    creator_id: str,
    day: str,
    chain: list[LiveSessionRow],
    group_index: int,
    max_gap: float | None,
) -> SuggestedGroup:
    ids = [r.id for r in chain]
    paths = [r.local_path for r in chain if r.local_path]
    sessions_arg = ",".join(ids)
    return SuggestedGroup(
        date=day,
        creator_id=creator_id,
        session_ids=ids,
        media_paths=paths,
        gap_minutes=int(max_gap) if max_gap is not None else None,
        room_id=chain[0].room_id,
        group_index=group_index,
        merge_command=f"media2text summarize merge --sessions {sessions_arg} --json",
    )
