"""Live pipeline status (aligned with CLI ``live status``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from media2text.api.deps import get_cfg, get_db
from media2text.core.config import AppConfig
from media2text.core.live.status import build_live_status

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/status")
def live_status(
    creator: str | None = Query(None, alias="creator"),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    return build_live_status(
        cfg,
        conn,
        creator_id=creator,
        command="api live status",
    )
