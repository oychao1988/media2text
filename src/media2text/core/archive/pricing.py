from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

PRICING_LOG_FILENAME = "pricing-experiment.jsonl"


@dataclass(frozen=True)
class PricingLogEntry:
    ts: str
    would_pay_99_cny: bool
    note: str | None
    creator_id: str | None
    session_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def pricing_log_path(workspace: Path) -> Path:
    return workspace / PRICING_LOG_FILENAME


def append_pricing_log(
    workspace: Path,
    *,
    would_pay_99_cny: bool,
    note: str | None = None,
    creator_id: str | None = None,
    session_id: str | None = None,
) -> PricingLogEntry:
    workspace.mkdir(parents=True, exist_ok=True)
    entry = PricingLogEntry(
        ts=datetime.now(timezone.utc).isoformat(),
        would_pay_99_cny=would_pay_99_cny,
        note=note,
        creator_id=creator_id,
        session_id=session_id,
    )
    path = pricing_log_path(workspace)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return entry
