from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COMPLIANCE_VERSION = "2026-05-22"
COMPLIANCE_FILENAME = ".compliance-accepted"


@dataclass(frozen=True)
class ComplianceRecord:
    accepted_at: str
    version: str

    def to_dict(self) -> dict:
        return {"accepted_at": self.accepted_at, "version": self.version}


def compliance_path(workspace: Path) -> Path:
    return workspace / COMPLIANCE_FILENAME


def is_compliance_accepted(workspace: Path) -> bool:
    path = compliance_path(workspace)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("accepted_at")) and payload.get("version") == COMPLIANCE_VERSION


def accept_compliance(workspace: Path) -> ComplianceRecord:
    workspace.mkdir(parents=True, exist_ok=True)
    record = ComplianceRecord(
        accepted_at=datetime.now(timezone.utc).isoformat(),
        version=COMPLIANCE_VERSION,
    )
    compliance_path(workspace).write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record
