"""Resolve creator history items and read transcript/summary sidecars."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

from media2text.api.security import workspace_rel
from media2text.api.services.history_media import _resolve_media_path
from media2text.api.services.sessions_list import _load_manifest, _manifest_live_by_id, _manifest_vod_by_id
from media2text.api.services.transcript import (
    read_summary_for_session,
    read_transcript_for_session,
    read_transcript_payload,
)
from media2text.core.live.transcript_writer import find_summary_sidecar
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo

HistoryKind = Literal["live", "vod"]


def resolve_history_media_path(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> Path | None:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return None
    manifest = _load_manifest(workspace, creator.sec_uid)
    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            return None
        m_entry = _manifest_live_by_id(manifest).get(item_id)
        manifest_path = m_entry.get("media_path") if m_entry else None
        return _resolve_media_path(
            workspace,
            local_path=session.local_path,
            temp_path=session.temp_path,
            manifest_path=manifest_path,
        )
    aweme = AwemeRepo(conn).get(item_id)
    if not aweme or aweme.creator_id != creator_id:
        return None
    m_entry = _manifest_vod_by_id(manifest).get(item_id)
    manifest_path = m_entry.get("media_path") if m_entry else None
    return _resolve_media_path(
        workspace, local_path=aweme.local_path, temp_path=None, manifest_path=manifest_path
    )


def read_history_transcript(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
    cfg=None,
) -> dict[str, Any]:
    if kind == "live":
        creator = CreatorRepo(conn).get(creator_id)
        if not creator:
            raise HTTPException(status_code=404, detail="history item not found")
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            raise HTTPException(status_code=404, detail="history item not found")
        try:
            return read_transcript_for_session(session, cfg=cfg, conn=conn)
        except HTTPException:
            raise HTTPException(status_code=404, detail="transcript not found") from None

    media = resolve_history_media_path(
        conn, workspace=workspace, creator_id=creator_id, kind=kind, item_id=item_id
    )
    if media is None:
        raise HTTPException(status_code=404, detail="history item not found")
    try:
        return read_transcript_payload(media)
    except HTTPException:
        raise HTTPException(status_code=404, detail="transcript not found") from None


def read_history_summary(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
    cfg=None,
) -> dict[str, Any]:
    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            raise HTTPException(status_code=404, detail="history item not found")
        try:
            text = read_summary_for_session(
                session, cfg=cfg, conn=conn, workspace=workspace
            )
        except HTTPException:
            raise HTTPException(status_code=404, detail="summary not found") from None
        return {"ok": True, "text": text, "summary_path": None}

    media = resolve_history_media_path(
        conn, workspace=workspace, creator_id=creator_id, kind=kind, item_id=item_id
    )
    if media is None:
        raise HTTPException(status_code=404, detail="history item not found")
    summary_path = find_summary_sidecar(media, workspace=workspace)
    if summary_path is None:
        raise HTTPException(status_code=404, detail="summary not found")
    try:
        text = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="summary read failed") from exc
    rel = workspace_rel(workspace, str(summary_path))
    return {"ok": True, "text": text, "summary_path": rel}
