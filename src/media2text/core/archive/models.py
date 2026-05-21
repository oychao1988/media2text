from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Hit:
    segment_id: int
    offset_sec: float | None
    start_sec: float | None
    session_id: str
    session_type: str
    creator_id: str
    sec_uid: str
    excerpt: str
    transcript_path: str
    open_path: str
    started_at: str | None

    def to_dict(self) -> dict:
        return asdict(self)
