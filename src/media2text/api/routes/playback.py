"""HLS playback: event playlist rewrite and part proxy with cloud fallback."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from media2text.api.deps import get_cfg, get_db
from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.api.services.cloud_byte_proxy import stream_cloud_file
from media2text.api.services.session_playback import (
    find_init_upload,
    find_m3u8_upload,
    find_part_upload,
)
from media2text.core.cloud.aliyundrive import AliyunDriveClient, DOWNLOAD_REFERER
from media2text.core.config import AppConfig
from media2text.core.live.playback_remux import (
    playback_mp4_is_fresh,
    playback_mp4_path,
    remux_hls_to_playback_mp4,
)
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import LiveSessionRepo

router = APIRouter(prefix="/sessions", tags=["playback"])

# ffmpeg event playlists may emit bare `seg-00001.m4s` or `parts/seg-00001.m4s`.
_PART_URI_RE = re.compile(r"(?:parts/)?seg-(\d+)\.m4s", re.IGNORECASE)
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


def _rewrite_init_uri(session_id: str, line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("#EXT-X-MAP:") and "init.mp4" in stripped:
        return re.sub(
            r'URI="init\.mp4"',
            f'URI="/api/sessions/{session_id}/init.mp4"',
            line,
        )
    if _INIT_URI_RE.fullmatch(stripped) or stripped.endswith("/init.mp4"):
        return f"/api/sessions/{session_id}/init.mp4"
    return None


def _part_local_available(session_dir: Path, part_index: int, part_row) -> bool:
    rel_name = (
        part_row.rel_path
        if part_row and part_row.rel_path
        else f"parts/seg-{part_index:05d}.m4s"
    )
    part_path = session_dir / rel_name
    if not part_path.is_file():
        part_path = session_dir / "parts" / f"seg-{part_index:05d}.m4s"
    return part_path.is_file() and part_path.stat().st_size > 0


def _part_indices_from_playlist(text: str) -> list[int]:
    indices: set[int] = set()
    for line in text.splitlines():
        idx = _part_index_from_uri(line.strip())
        if idx is not None:
            indices.add(idx)
    return sorted(indices)


def _missing_playback_parts(
    conn,
    cfg: AppConfig,
    *,
    session_id: str,
    session_dir: Path,
    raw_m3u8: str,
) -> list[int]:
    indices = _part_indices_from_playlist(raw_m3u8)
    if not indices:
        indices = [
            row.part_index
            for row in SegmentManifestRepo(conn).list_parts(session_id)
            if row.part_index
        ]
    missing: list[int] = []
    repo = SegmentManifestRepo(conn)
    for part_index in indices:
        part_row = repo.get_part(session_id, part_index)
        if _part_local_available(session_dir, part_index, part_row):
            continue
        upload = find_part_upload(conn, session_id=session_id, part_index=part_index)
        if upload and upload.cloud_file_id and cfg.aliyundrive.enabled:
            continue
        missing.append(part_index)
    return missing


def _rewrite_m3u8(
    text: str,
    *,
    session_id: str,
) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        init_line = _rewrite_init_uri(session_id, line)
        if init_line is not None:
            out_lines.append(init_line)
            continue
        if not stripped or stripped.startswith("#"):
            out_lines.append(line)
            continue
        part_index = _part_index_from_uri(stripped)
        if part_index is not None:
            out_lines.append(f"/api/sessions/{session_id}/parts/{part_index}")
            continue
        out_lines.append(line)
    body = "\n".join(out_lines)
    if not body.endswith("\n"):
        body += "\n"
    return body


def _stream_cloud_upload(
    cfg: AppConfig,
    upload,
    *,
    range_header: str | None,
    media_type: str = "video/mp4",
):
    if not upload or not upload.cloud_file_id or not cfg.aliyundrive.enabled:
        return None
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return None
    try:
        with AliyunDriveClient.open(token_path) as client:
            return stream_cloud_file(
                client,
                str(upload.cloud_file_id),
                range_header=range_header,
                media_type=media_type,
            )
    except RuntimeError:
        raise HTTPException(status_code=502, detail="cloud playback unavailable") from None
    except Exception:  # noqa: BLE001
        return None


def _fetch_cloud_m3u8_text(cfg: AppConfig, upload) -> str:
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        raise FileNotFoundError("aliyundrive token missing")
    with AliyunDriveClient.open(token_path) as client:
        url = client.get_download_url(str(upload.cloud_file_id))
        resp = httpx.get(url, headers={"Referer": DOWNLOAD_REFERER}, timeout=30.0)
        if resp.status_code >= 400:
            raise RuntimeError(f"cloud m3u8 fetch failed {resp.status_code}")
        return resp.text


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
    if master.is_file():
        raw = master.read_text(encoding="utf-8")
    else:
        upload = find_m3u8_upload(conn, session_id=session_id)
        if not upload or not upload.cloud_file_id or not cfg.aliyundrive.enabled:
            raise HTTPException(status_code=404, detail="playlist not found")
        try:
            raw = _fetch_cloud_m3u8_text(cfg, upload)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="playlist not found") from None
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail="cloud playlist unavailable") from exc

    rewritten = _rewrite_m3u8(raw, session_id=session_id)
    missing_parts = _missing_playback_parts(
        conn,
        cfg,
        session_id=session_id,
        session_dir=session_dir,
        raw_m3u8=raw,
    )
    headers: dict[str, str] = {"Cache-Control": "no-cache"}
    if missing_parts:
        headers["X-M2T-Missing-Parts"] = ",".join(str(i) for i in missing_parts)
    return Response(
        content=rewritten,
        media_type="application/vnd.apple.mpegurl",
        headers=headers,
    )


@router.get("/{session_id}/parts/{part_index}", response_model=None)
def get_playback_part(
    session_id: str,
    part_index: int,
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
):
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
                    media_type="video/mp4",
                    headers={"Accept-Ranges": "bytes"},
                )
        return FileResponse(
            path=part_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"},
        )

    if part_row and part_row.state in ("uploaded", "local_deleted"):
        upload = find_part_upload(conn, session_id=session_id, part_index=part_index)
        proxied = _stream_cloud_upload(
            cfg,
            upload,
            range_header=request.headers.get("range"),
        )
        if proxied is not None:
            return proxied

    raise HTTPException(status_code=404, detail="part not found")


@router.get("/{session_id}/init.mp4", response_model=None)
def get_playback_init(
    session_id: str,
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
):
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    session_dir = _resolve_session_dir(row)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="session_dir not found")

    init_path = session_dir / "init.mp4"
    if init_path.is_file():
        return FileResponse(
            path=init_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"},
        )

    upload = find_init_upload(conn, session_id=session_id)
    proxied = _stream_cloud_upload(
        cfg,
        upload,
        range_header=request.headers.get("range"),
    )
    if proxied is not None:
        return proxied

    raise HTTPException(status_code=404, detail="init not found")


@router.get("/{session_id}/playback.mp4", response_model=None)
def get_playback_mp4(
    session_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> FileResponse:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    session_dir = _resolve_session_dir(row)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="session_dir not found")

    master = session_dir / "master.m3u8"
    if not master.is_file():
        raise HTTPException(status_code=404, detail="playlist not found")

    try:
        out = remux_hls_to_playback_mp4(
            session_dir,
            ffmpeg=cfg.live.ffmpeg_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        path=out,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
    )


@router.get("/{session_id}/playback.mp4/status")
def get_playback_mp4_status(
    session_id: str,
    conn=Depends(get_db),
) -> dict:
    row = LiveSessionRepo(conn).get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    session_dir = _resolve_session_dir(row)
    if session_dir is None:
        raise HTTPException(status_code=404, detail="session_dir not found")
    out = playback_mp4_path(session_dir) if session_dir else None
    ready = bool(out and out.is_file() and playback_mp4_is_fresh(session_dir))
    return {"ready": ready, "path": str(out) if ready else None}
