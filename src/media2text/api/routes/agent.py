from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import MessageRow, SessionDB, parse_binding
from media2text.agent.turn_registry import turn_registry
from media2text.api.deps import get_cfg, get_db
from media2text.api.services.agent_stream_hub import agent_stream_hub
from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

_VALID_CONTEXT_MODES = frozenset({"transcript", "summary", "both"})
_VALID_ROLES = frozenset({"user", "assistant", "system", "tool"})


class ThreadCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    creator_id: str | None = Field(default=None, alias="creatorId")
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


class TurnBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str
    sidebar_creator_id: str | None = Field(default=None, alias="sidebarCreatorId")
    retry: bool = False
    after_message_id: str | None = Field(default=None, alias="afterMessageId")


class ActivateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    creator_id: str | None = Field(default=None, alias="creatorId")
    session_id: str | None = Field(default=None, alias="sessionId")
    session_kind: str | None = Field(default=None, alias="sessionKind")
    transcript_path: str | None = Field(default=None, alias="transcriptPath")
    summary_path: str | None = Field(default=None, alias="summaryPath")
    context_mode: str | None = Field(default=None, alias="contextMode")
    clear_session: bool = Field(default=False, alias="clearSession")
    attachments: list[dict[str, Any]] | None = None


def _thread_dict(row) -> dict[str, Any]:
    binding = parse_binding(row["active_binding_json"])
    attachments = binding.get("attachments")
    if not isinstance(attachments, list):
        attachments = None
    return {
        "id": row["display_thread_id"],
        "sessionId": binding.get("session_id"),
        "creator_id": row["creator_id"],
        "creatorId": row["creator_id"],
        "session_id": binding.get("session_id"),
        "title": row["title"],
        "provider_name": binding.get("provider_name"),
        "providerName": binding.get("provider_name"),
        "model": binding.get("model", "auto"),
        "context_mode": binding.get("context_mode", "both"),
        "contextMode": binding.get("context_mode", "both"),
        "session_kind": binding.get("session_kind"),
        "sessionKind": binding.get("session_kind"),
        "transcript_path": binding.get("transcript_path"),
        "transcriptPath": binding.get("transcript_path"),
        "summary_path": binding.get("summary_path"),
        "summaryPath": binding.get("summary_path"),
        "attachments": attachments,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message_dict(row, *, display_thread_id: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "thread_id": display_thread_id,
        "threadId": display_thread_id,
        "role": row["role"],
        "content": row["content"],
        "thinking_text": row["thinking_text"],
        "thinkingText": row["thinking_text"],
        "duration_ms": row["duration_ms"],
        "durationMs": row["duration_ms"],
        "created_at": row["created_at"],
        "tool_name": row["tool_name"],
        "toolName": row["tool_name"],
    }


def _get_db_session(
    conn=Depends(get_db),
    cfg: AppConfig = Depends(get_cfg),
) -> SessionDB:
    return SessionDB(conn, cfg=cfg)


def _assert_thread_exists(db: SessionDB, thread_id: str) -> None:
    if db.get_thread_by_display_id(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")


def _run_turn(
    cfg: AppConfig,
    thread_id: str,
    text: str,
    turn_id: str,
    *,
    retry_after_message_id: str | None = None,
) -> None:
    handle = turn_registry.get(turn_id)
    supervisor = handle.supervisor if handle else None

    def emit(event: dict[str, Any]) -> None:
        agent_stream_hub.publish(event, thread_id=thread_id)

    conn = open_db(cfg)
    try:
        db = SessionDB(conn, cfg=cfg)
        agent = AIAgent(db, cfg, supervisor=supervisor)
        cancel = handle.cancel if handle else None
        agent.run_conversation(
            display_thread_id=thread_id,
            user_text=text,
            turn_id=turn_id,
            retry_after_message_id=retry_after_message_id,
            cancel_event=cancel,
            emit=emit,
        )
    except Exception:
        logger.exception("agent turn failed thread=%s turn=%s", thread_id, turn_id)
    finally:
        conn.close()
        turn_registry.unregister(turn_id)


def _supervisor(request: Request) -> MonitorSupervisor | None:
    sup = getattr(request.app.state, "supervisor", None)
    if sup is None:
        api_app = getattr(request.app.state, "api_app", None)
        if api_app is not None:
            sup = getattr(api_app.state, "supervisor", None)
    return sup


@router.get("/threads")
def list_threads(
    creator_id: str | None = Query(None, alias="creatorId"),
    session_id: str | None = Query(None, alias="sessionId"),
    db: SessionDB = Depends(_get_db_session),
) -> dict:
    threads = [_thread_dict(t) for t in db.list_threads(creator_id=creator_id, live_session_id=session_id)]
    return {"ok": True, "threads": threads}


@router.post("/threads")
def create_thread(
    body: ThreadCreateBody,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if body.context_mode not in _VALID_CONTEXT_MODES:
        raise HTTPException(
            status_code=400,
            detail="contextMode must be transcript, summary, or both",
        )
    if body.creator_id is not None and not CreatorRepo(conn).get(body.creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    db = SessionDB(conn, cfg=cfg)
    thread_id = str(uuid.uuid4())
    db.create_session(
        display_thread_id=thread_id,
        title=body.title,
        creator_id=body.creator_id,
        provider_name=body.provider_name,
        model=body.model,
        context_mode=body.context_mode,
        live_session_id=body.session_id,
    )
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    return {"ok": True, "thread": _thread_dict(row)}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, db: SessionDB = Depends(_get_db_session)) -> dict:
    row = db.get_thread_by_display_id(thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True, "thread": _thread_dict(row)}


@router.patch("/threads/{thread_id}")
def patch_thread(
    thread_id: str,
    payload: dict[str, Any],
    db: SessionDB = Depends(_get_db_session),
) -> dict:
    body = ThreadPatchBody.model_validate(payload)
    if body.context_mode is not None and body.context_mode not in _VALID_CONTEXT_MODES:
        raise HTTPException(
            status_code=400,
            detail="contextMode must be transcript, summary, or both",
        )
    if db.get_thread_by_display_id(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    db.update_session(
        thread_id,
        title=body.title,
        provider_name=body.provider_name,
        model=body.model,
        context_mode=body.context_mode,
        live_session_id=body.session_id,
        clear_live_session=body.clear_session,
    )
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    return {"ok": True, "thread": _thread_dict(row)}


@router.patch("/threads/{thread_id}/activate")
def activate_thread(
    thread_id: str,
    payload: dict[str, Any],
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    body = ActivateBody.model_validate(payload)
    if body.context_mode is not None and body.context_mode not in _VALID_CONTEXT_MODES:
        raise HTTPException(
            status_code=400,
            detail="contextMode must be transcript, summary, or both",
        )
    if body.creator_id is not None and not CreatorRepo(conn).get(body.creator_id):
        raise HTTPException(status_code=404, detail="creator not found")
    db = SessionDB(conn, cfg=cfg)
    if db.get_thread_by_display_id(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    db.activate_thread(
        thread_id,
        creator_id=body.creator_id,
        live_session_id=body.session_id,
        clear_live_session=body.clear_session,
        session_kind=body.session_kind,
        transcript_path=body.transcript_path,
        summary_path=body.summary_path,
        context_mode=body.context_mode,
        attachments=body.attachments,
    )
    row = db.get_thread_by_display_id(thread_id)
    assert row is not None
    return {"ok": True, "thread": _thread_dict(row)}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, db: SessionDB = Depends(_get_db_session)) -> dict:
    if not db.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True, "deleted": True, "thread_id": thread_id}


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: str, db: SessionDB = Depends(_get_db_session)) -> dict:
    _assert_thread_exists(db, thread_id)
    messages = [_message_dict(m, display_thread_id=thread_id) for m in db.get_messages(thread_id)]
    return {"ok": True, "thread_id": thread_id, "messages": messages}


@router.post("/threads/{thread_id}/messages")
def create_message(
    thread_id: str,
    body: MessageCreateBody,
    db: SessionDB = Depends(_get_db_session),
) -> dict:
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail="role must be user, assistant, system, or tool",
        )
    _assert_thread_exists(db, thread_id)
    session_id = db.get_active_session_for_thread(thread_id)
    mid = db.append_message(
        session_id,
        MessageRow(
            role=body.role,
            content=body.content,
            thinking_text=body.thinking_text,
            duration_ms=body.duration_ms,
        ),
    )
    msg_row = next(m for m in db.get_messages(thread_id) if m["id"] == mid)
    return {"ok": True, "message": _message_dict(msg_row, display_thread_id=thread_id)}


@router.post("/threads/{thread_id}/turn")
def start_turn(
    thread_id: str,
    body: TurnBody,
    background_tasks: BackgroundTasks,
    request: Request,
    db: SessionDB = Depends(_get_db_session),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    if body.retry and not body.after_message_id:
        raise HTTPException(status_code=400, detail="afterMessageId required for retry")
    turn_id = str(uuid.uuid4())
    turn_registry.register(
        turn_id=turn_id,
        thread_id=thread_id,
        supervisor=_supervisor(request),
    )
    background_tasks.add_task(
        _run_turn,
        cfg,
        thread_id,
        body.text,
        turn_id,
        retry_after_message_id=body.after_message_id if body.retry else None,
    )
    return {"ok": True, "turnId": turn_id}


@router.post("/turns/{turn_id}/cancel")
def cancel_turn(turn_id: str) -> dict:
    if not turn_registry.cancel(turn_id):
        raise HTTPException(status_code=404, detail="turn not found")
    return {"ok": True, "turnId": turn_id, "cancelled": True}


class ApprovalBody(BaseModel):
    approved: bool


@router.post("/approvals/{approval_id}")
def resolve_approval(approval_id: str, body: ApprovalBody) -> dict:
    from media2text.agent.approval import GLOBAL_APPROVAL_REGISTRY

    ok = GLOBAL_APPROVAL_REGISTRY.resolve(approval_id, approved=body.approved)
    if not ok:
        raise HTTPException(status_code=404, detail="approval not found or already resolved")
    return {"ok": True, "approvalId": approval_id, "approved": body.approved}


def mark_deprecated(response: Response | None) -> None:
    if response is None:
        return
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/agent/threads>; rel="successor-version"'
