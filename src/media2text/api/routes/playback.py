"""HLS playback: event playlist rewrite and part proxy with cloud fallback."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from media2text.api.deps import get_cfg, get_db
from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.cloud.aliyundrive import AliyunDriveClient
from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CloudUploadRepo, LiveSessionRepo

router = APIRouter(prefix="/sessions", tags=["playback"])

_PART_URI_RE = re.compile(r"parts/seg-(\d+)\.m4s", re.IGNORECASE)
_INIT_URI_RE = re.compile(r"init\.mp4", re.IGNORECASE)


def _resolve_session_dir(row) -> Path | None:
    if row.session_dir:
        candidate = Path(row.session_dir)
        if candidate.is_dir():
            return candidate
    if row.local_path:
        candidate = Path(row.local_path)
        if candidate.is_dir():
            return candidate
        if candidate.is_file():
            return candidate.parent
    if row.temp_path:
        candidate = Path(row.temp_path)
        return candidate.parent if candidate.is_file() else candidate
    return None


def _part_index_from_uri(uri: str) -> int | None:
    match = _PART_URI_RE.search(uri.strip())
    if not match:
        return None
    return int(match.group(1))


def _rewrite_m3u8(
    text: str,
    *,
    session_id: str,
    session_dir: Path,
    workspace,
) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(line)
            continue
        part_index = _part_index_from_uri(stripped)
        if part_index is not None:
            out_lines.append(f"/api/sessions/{session_id}/parts/{part_index}")
            continue
        if _INIT_URI_RE.fullmatch(stripped) or stripped.endswith("/init.mp4"):
            init_path = session_dir / "init.mp4"
            if init_path.is_file():
                rel = workspace_rel(workspace, str(init_path))
                if rel:
                    out_lines.append(f"/api/media?path={rel}")
                    continue
        out_lines.append(line)
    body = "\n".join(out_lines)
    if not body.endswith("\n"):
        body += "\n"
    return body


def _cloud_part_redirect(cfg: AppConfig, conn, *, session_id: str, part_index: int):
    upload = None
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.part_index == part_index and row.upload_status == "done" and row.cloud_file_id:
            upload = row
            break
    if upload is None:
        part = SegmentManifestRepo(conn).get_part(session_id, part_index)
        if part and part.cloud_path:
            for row in CloudUploadRepo(conn).list_for_session(session_id):
                if (
                    row.upload_status == "done"
                    and row.cloud_file_id
                    and row.file_kind == "m4s"
                    and f"seg-{part_index:05d}.m4s" in (row.file_name or "")
                ):
                    upload = row
                    break
    if upload is None or not upload.cloud_file_id:
        return None
    if not cfg.aliyundrive.enabled:
        return None
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return None
    try:
        with AliyunDriveClient.open(token_path) as client:
            url = client.get_download_url(str(upload.cloud_file_id))
    except Exception:  # noqa: BLE001
        return None
    return RedirectResponse(url=url, status_code=302)


@router.get("/{session_id}/playback.m3u8")
def get_playback_m3u8(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> Response:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    session_dir = _resolve_session_dir(row)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="session_dir not found")
    master = session_dir / "master.m3u8"
    if not master.is_file():
        raise HTTPException(status_code=404, detail="playlist not found")

    raw = master.read_text(encoding="utf-8")
    ws = cfg.ensure_workspace()
    rewritten = _rewrite_m3u8(
        raw,
        session_id=session_id,
        session_dir=session_dir,
        workspace=ws,
    )
    return Response(
        content=rewritten,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/{session_id}/parts/{part_index}", response_model=None)
def get_playback_part(
    session_id: str,
    part_index: int,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> FileResponse | RedirectResponse:
    if part_index < 1:
        raise HTTPException(status_code=404, detail="part not found")

    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    session_dir = _resolve_session_dir(row)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="session_dir not found")

    part_row = SegmentManifestRepo(conn).get_part(session_id, part_index)
    rel_name = (
        part_row.rel_path
        if part_row and part_row.rel_path
        else f"parts/seg-{part_index:05d}.m4s"
    )
    part_path = session_dir / rel_name
    if not part_path.is_file():
        part_path = session_dir / "parts" / f"seg-{part_index:05d}.m4s"

    if part_path.is_file():
        ws = cfg.ensure_workspace()
        rel = workspace_rel(ws, str(part_path))
        if rel:
            try:
                safe_workspace_path(ws, rel)
            except HTTPException:
                pass
            else:
                return FileResponse(
                    path=part_path,
                    media_type="video/iso.segment",
                    headers={"Accept-Ranges": "bytes"},
                )
        return FileResponse(
            path=part_path,
            media_type="video/iso.segment",
            headers={"Accept-Ranges": "bytes"},
        )

    if part_row and part_row.state in ("uploaded", "local_deleted"):
        redirect = _cloud_part_redirect(cfg, conn, session_id=session_id, part_index=part_index)
        if redirect is not None:
            return redirect

    raise HTTPException(status_code=404, detail="part not found")
