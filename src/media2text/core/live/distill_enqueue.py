"""DB-only creator distill job enqueue (no agent imports)."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo


def maybe_enqueue_evolve_job(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    source_id: str,
    trigger: str,
) -> str | None:
    """Enqueue evolve when trigger is listed in distill.evolve_on (pending until CLI/API drain)."""
    allowed = cfg.desktop.agent.distill.evolve_on or []
    if trigger not in allowed:
        return None
    if not CreatorRepo(conn).get(creator_id):
        return None
    return CreatorAgentJobRepo(conn).enqueue_evolve(
        creator_id=creator_id,
        source_id=source_id,
        trigger=trigger,
    )
