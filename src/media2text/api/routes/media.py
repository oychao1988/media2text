"""Workspace media files with HTTP Range support."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse

from media2text.api.deps import get_cfg, get_db
from media2text.api.services.history_media import try_cloud_media_range
from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.config import AppConfig

router = APIRouter(tags=["media"])

_EXT_MEDIA_TYPES = {
    ".flv": "video/x-flv",
    ".mp4": "video/mp4",
    ".m4s": "video/mp4",
    ".m3u8": "application/vnd.apple.mpegurl",
    ".webm": "video/webm",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}

_GALLERY_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _EXT_MEDIA_TYPES:
        return _EXT_MEDIA_TYPES[ext]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _parse_range_header(
    range_header: str | None,
    size: int,
) -> tuple[int, int] | None:
    if not range_header or not range_header.strip().lower().startswith("bytes="):
        return None
    spec = range_header.strip()[6:]
    if "," in spec:
        raise HTTPException(status_code=416, detail="multiple ranges not supported")
    start_s, _, end_s = spec.partition("-")
    try:
        if start_s and end_s:
            start, end = int(start_s), int(end_s)
        elif start_s:
            start, end = int(start_s), size - 1
        elif end_s:
            suffix = int(end_s)
            start = max(0, size - suffix)
            end = size - 1
        else:
            return None
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="invalid Range") from exc
    if start < 0 or end >= size or start > end:
        raise HTTPException(status_code=416, detail="range not satisfiable")
    return start, end


@router.get("/media/gallery")
def list_gallery_images(
    path: str = Query(..., description="Workspace-relative gallery directory"),
    cfg: AppConfig = Depends(get_cfg),
) -> dict:
    ws = cfg.ensure_workspace()
    target = safe_workspace_path(ws, path)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="gallery not found")
    images: list[str] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name):
        if child.is_file() and child.suffix.lower() in _GALLERY_SUFFIXES:
            rel = workspace_rel(ws, child)
            if rel:
                images.append(rel)
    return {"ok": True, "path": path, "images": images}


@router.get("/media")
def get_media(
    path: str = Query(..., description="Workspace-relative media path"),
    range: str | None = Header(None, alias="Range"),
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> Response:
    ws = cfg.ensure_workspace()
    target = safe_workspace_path(ws, path)
    if not target.is_file():
        cloud_resp = try_cloud_media_range(
            cfg,
            conn,
            workspace_rel_path=path,
            range_header=range,
        )
        if cloud_resp is not None:
            return cloud_resp
        raise HTTPException(status_code=404, detail="file not found")

    size = target.stat().st_size
    content_type = _content_type(target)
    parsed = _parse_range_header(range, size)

    if parsed is None:
        return FileResponse(
            path=target,
            media_type=content_type,
            headers={"Accept-Ranges": "bytes"},
        )

    start, end = parsed
    length = end - start + 1
    with target.open("rb") as fh:
        fh.seek(start)
        data = fh.read(length)

    return Response(
        content=data,
        status_code=206,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
    )
