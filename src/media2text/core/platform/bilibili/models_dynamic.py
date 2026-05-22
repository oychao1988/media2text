from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedDynamic:
    dynamic_id: str
    dynamic_type: str
    text: str
    image_urls: list[str] = field(default_factory=list)
    bvid: str | None = None
    opus_id: str | None = None
    published_at: str | None = None
    pub_ts: int | None = None
