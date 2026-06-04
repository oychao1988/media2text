from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from media2text.api.config_dto import _llm_providers_dto
from media2text.api.deps import get_cfg, get_db
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, DesktopChatRepo

router = APIRouter(prefix="/chat", tags=["chat"])

_VALID_CONTEXT_MODES = frozenset({"transcript", "summary", "both"})
_VALID_ROLES = frozenset({"user", "assistant", "system", "tool"})


class ThreadCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    creator_id: str = Field(alias="creatorId")
    session_id: str | None = Field(default=None, alias="sessionId")
    title: str | None = None
    provider_name: str | None = Field(default=None, alias="providerName")
    model: str = "auto"
    context_mode: str = Field(default="both", alias="contextMode")


class ThreadPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    provider_name: str | None = Field(default=None, alias="providerName")
    model: str | None = None
    context_mode: str | None = Field(default=None, alias="contextMode")
    session_id: str | None = Field(default=None, alias="sessionId")
    clear_session: bool = Field(default=False, alias="clearSession")


class MessageCreateBody(BaseModel):
    role: str
    content: str
    thinking_text: str | None = Field(default=None, alias="thinkingText")
    duration_ms: int | None = Field(default=None, alias="durationMs")


def _thread_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "session_id": row.session_id,
        "title": row.title,
        "provider_name": row.provider_name,
        "model": row.model,
        "context_mode": row.context_mode,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _message_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "role": row.role,
        "content": row.content,
        "thinking_text": row.thinking_text,
        "duration_ms": row.duration_ms,
        "created_at": row.created_at,
    }


@router.get("/providers")
def list_providers(cfg: AppConfig = Depends(get_cfg)) -> dict:
    return {"ok": True, "providers": _llm_providers_dto(cfg)}


@router.get("/threads")
def list_threads(
    creator_id: str | None = Query(None, alias="creatorId"),
    session_id: str | None = Query(None, alias="sessionId"),
    conn=Depends(get_db),
) -> dict:
    repo = DesktopChatRepo(conn)
    threads = [_thread_dict(t) for t in repo.list_threads(creator_id=creator_id, session_id=session_id)]
    return {"ok": True, "threads": threads}


@router.post("/threads")
def create_thread(body: ThreadCreateBody, conn=Depends(get_db)) -> dict:
    if body.context_mode not in _VALID_CONTEXT_MODES:
        raise HTTPException(
            status_code=400,
            detail="contextMode must be transcript, summary, or both",
        )
    if not CreatorRepo(conn).get(body.creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    repo = DesktopChatRepo(conn)
    tid = repo.create_thread(
        creator_id=body.creator_id,
        session_id=body.session_id,
        title=body.title,
        provider_name=body.provider_name,
        model=body.model,
        context_mode=body.context_mode,
    )
    row = repo.get_thread(tid)
    assert row is not None
    return {"ok": True, "thread": _thread_dict(row)}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, conn=Depends(get_db)) -> dict:
    row = DesktopChatRepo(conn).get_thread(thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True, "thread": _thread_dict(row)}


@router.patch("/threads/{thread_id}")
def patch_thread(
    thread_id: str,
    payload: dict[str, Any],
    conn=Depends(get_db),
) -> dict:
    body = ThreadPatchBody.model_validate(payload)
    if body.context_mode is not None and body.context_mode not in _VALID_CONTEXT_MODES:
        raise HTTPException(
            status_code=400,
            detail="contextMode must be transcript, summary, or both",
        )
    repo = DesktopChatRepo(conn)
    if not repo.get_thread(thread_id):
        raise HTTPException(status_code=404, detail="thread not found")
    repo.update_thread(
        thread_id,
        title=body.title,
        provider_name=body.provider_name,
        model=body.model,
        context_mode=body.context_mode,
        session_id=body.session_id,
        clear_session=body.clear_session,
    )
    row = repo.get_thread(thread_id)
    assert row is not None
    return {"ok": True, "thread": _thread_dict(row)}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, conn=Depends(get_db)) -> dict:
    if not DesktopChatRepo(conn).delete_thread(thread_id):
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True, "deleted": True, "thread_id": thread_id}


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: str, conn=Depends(get_db)) -> dict:
    repo = DesktopChatRepo(conn)
    if not repo.get_thread(thread_id):
        raise HTTPException(status_code=404, detail="thread not found")
    messages = [_message_dict(m) for m in repo.list_messages(thread_id)]
    return {"ok": True, "thread_id": thread_id, "messages": messages}


@router.post("/threads/{thread_id}/messages")
def create_message(
    thread_id: str,
    body: MessageCreateBody,
    conn=Depends(get_db),
) -> dict:
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail="role must be user, assistant, system, or tool",
        )
    repo = DesktopChatRepo(conn)
    if not repo.get_thread(thread_id):
        raise HTTPException(status_code=404, detail="thread not found")
    mid = repo.add_message(
        thread_id,
        role=body.role,
        content=body.content,
        thinking_text=body.thinking_text,
        duration_ms=body.duration_ms,
    )
    messages = repo.list_messages(thread_id)
    msg = next(m for m in messages if m.id == mid)
    return {"ok": True, "message": _message_dict(msg)}
