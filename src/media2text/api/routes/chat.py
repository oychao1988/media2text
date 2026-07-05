from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from media2text.api.config_dto import _llm_providers_dto
from media2text.api.deps import get_cfg, get_db
from media2text.api.routes import agent as agent_routes
from media2text.core.config import AppConfig

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    deprecated=True,
)


@router.get("/providers")
def list_providers(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return {"ok": True, "providers": _llm_providers_dto(cfg)}


@router.get("/threads")
def list_threads(
    response: Response,
    creator_id: str | None = Query(None, alias="creatorId"),
    session_id: str | None = Query(None, alias="sessionId"),
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.list_threads(creator_id=creator_id, session_id=session_id, db=db)


@router.post("/threads")
def create_thread(
    response: Response,
    body: agent_routes.ThreadCreateBody,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.create_thread(body=body, cfg=cfg, conn=conn)


@router.get("/threads/{thread_id}")
def get_thread(
    response: Response,
    thread_id: str,
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.get_thread(thread_id=thread_id, db=db)


@router.patch("/threads/{thread_id}")
def patch_thread(
    response: Response,
    thread_id: str,
    payload: dict[str, Any],
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.patch_thread(thread_id=thread_id, payload=payload, db=db)


@router.delete("/threads/{thread_id}")
def delete_thread(
    response: Response,
    thread_id: str,
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.delete_thread(thread_id=thread_id, db=db)


@router.get("/threads/{thread_id}/messages")
def list_messages(
    response: Response,
    thread_id: str,
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.list_messages(thread_id=thread_id, db=db)


@router.post("/threads/{thread_id}/messages")
def create_message(
    response: Response,
    thread_id: str,
    body: agent_routes.MessageCreateBody,
    db=Depends(agent_routes._get_db_session),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.create_message(thread_id=thread_id, body=body, db=db)


@router.post("/threads/{thread_id}/turn")
def start_turn(
    response: Response,
    thread_id: str,
    body: agent_routes.TurnBody,
    background_tasks: BackgroundTasks,
    db=Depends(agent_routes._get_db_session),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    agent_routes.mark_deprecated(response)
    return agent_routes.start_turn(
        thread_id=thread_id,
        body=body,
        background_tasks=background_tasks,
        db=db,
        cfg=cfg,
    )
