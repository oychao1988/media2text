"""distill_state.json API cache (DB is source of truth)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2text.agent.creator_distill.atomic import atomic_write_text
from media2text.core.storage.models import CreatorAgentJobRow


def refresh_distill_state_cache(
    profile_dir: Path,
    *,
    creator_id: str,
    latest_job: CreatorAgentJobRow | None,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "creator_id": creator_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_bootstrap": None,
    }
    if latest_job:
        payload["latest_bootstrap"] = {
            "id": latest_job.id,
            "status": latest_job.status,
            "trigger": latest_job.trigger,
            "updated_at": latest_job.updated_at,
        }
    if extra:
        payload.update(extra)
    out = profile_dir / "distill_state.json"
    atomic_write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return out
