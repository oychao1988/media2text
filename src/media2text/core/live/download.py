"""Download HLS live session parts from local disk or Aliyun Drive."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from media2text.core.cloud.aliyundrive import AliyunDriveClient
from media2text.core.config import AppConfig
from media2text.core.ffmpeg import concat_to_mp4
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CloudUploadRepo, LiveSessionRepo


def resolve_session_dir(row) -> Path | None:
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


def parse_parts_selector(parts: str, available: list[int]) -> list[int]:
    raw = parts.strip().lower()
    if not available:
        raise ValueError("no_parts_available")
    if raw == "all":
        return sorted(available)
    selected: list[int] = []
    for piece in parts.split(","):
        piece = piece.strip()
        if not piece:
            continue
        idx = int(piece)
        if idx not in available:
            raise ValueError(f"part_not_found:{idx}")
        selected.append(idx)
    if not selected:
        raise ValueError("no_parts_selected")
    return sorted(set(selected))


def find_cloud_upload_for_part(conn, session_id: str, part_index: int):
    uploads = CloudUploadRepo(conn).list_for_session(session_id)
    for row in uploads:
        if row.part_index == part_index and row.upload_status == "done" and row.cloud_file_id:
            return row
    part = SegmentManifestRepo(conn).get_part(session_id, part_index)
    if part and part.cloud_path:
        for row in uploads:
            if (
                row.upload_status == "done"
                and row.cloud_file_id
                and row.file_kind == "m4s"
                and f"seg-{part_index:05d}.m4s" in (row.file_name or "")
            ):
                return row
    return None


def _part_rel_path(part_row, part_index: int) -> str:
    if part_row and part_row.rel_path:
        return part_row.rel_path
    return f"parts/seg-{part_index:05d}.m4s"


def _part_local_path(session_dir: Path, part_index: int, rel_path: str) -> Path:
    candidate = session_dir / rel_path
    if candidate.is_file():
        return candidate
    fallback = session_dir / "parts" / f"seg-{part_index:05d}.m4s"
    return fallback


def _download_cloud_part(
    client: AliyunDriveClient,
    *,
    cloud_file_id: str,
    dest: Path,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = client.download_bytes(cloud_file_id)
    dest.write_bytes(data)


def _resolve_output_dir(
    *,
    session_dir: Path,
    keep_local: bool,
    output_dir: Path | None,
) -> tuple[Path, Path | None]:
    """Return (output_dir, temp_dir_to_cleanup)."""
    if keep_local:
        out = session_dir / "parts"
        out.mkdir(parents=True, exist_ok=True)
        return out, None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir, None
    temp = Path(tempfile.mkdtemp(prefix="m2t-live-dl-"))
    return temp, temp


def download_live_session(
    cfg: AppConfig,
    conn,
    *,
    session_id: str,
    parts: str = "all",
    keep_local: bool = False,
    merge: bool = False,
    output_dir: Path | None = None,
    client_factory: Callable[[Path], AliyunDriveClient] | None = None,
) -> dict[str, Any]:
    sessions = LiveSessionRepo(conn)
    session = sessions.get(session_id)
    if not session:
        return {
            "ok": False,
            "command": "live download",
            "error": "session_not_found",
            "session_id": session_id,
        }

    session_dir = resolve_session_dir(session)
    if session_dir is None:
        return {
            "ok": False,
            "command": "live download",
            "error": "session_dir_not_found",
            "session_id": session_id,
        }

    manifest = SegmentManifestRepo(conn)
    all_parts = manifest.list_parts(session_id)
    available = [p.part_index for p in all_parts]
    if not available:
        available = sorted(
            row.part_index
            for row in CloudUploadRepo(conn).list_for_session(session_id)
            if row.part_index is not None and row.upload_status == "done"
        )

    try:
        part_indices = parse_parts_selector(parts, available)
    except ValueError as exc:
        code = str(exc)
        return {
            "ok": False,
            "command": "live download",
            "error": code.split(":")[0] if ":" in code else code,
            "session_id": session_id,
            "detail": code,
        }

    out_dir, temp_dir = _resolve_output_dir(
        session_dir=session_dir,
        keep_local=keep_local,
        output_dir=output_dir,
    )

    downloaded: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    part_paths: list[Path] = []

    token_path = cfg.aliyundrive_token_path()
    use_cloud = cfg.aliyundrive.enabled and token_path.is_file()

    def _download_parts(client: AliyunDriveClient | None) -> None:
        for part_index in part_indices:
            part_row = manifest.get_part(session_id, part_index)
            rel_path = _part_rel_path(part_row, part_index)
            local_path = _part_local_path(session_dir, part_index, rel_path)
            dest = out_dir / Path(rel_path).name if not keep_local else local_path

            if local_path.is_file():
                if not keep_local and dest != local_path:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local_path, dest)
                    part_paths.append(dest)
                else:
                    part_paths.append(local_path)
                downloaded.append(
                    {
                        "part_index": part_index,
                        "source": "local",
                        "path": str(part_paths[-1]),
                    }
                )
                continue

            upload = find_cloud_upload_for_part(conn, session_id, part_index)
            if upload is None or not upload.cloud_file_id:
                errors.append(
                    {
                        "part_index": part_index,
                        "error": "part_not_available",
                    }
                )
                continue

            if client is None:
                errors.append(
                    {
                        "part_index": part_index,
                        "error": "cloud_download_unavailable",
                    }
                )
                continue

            try:
                _download_cloud_part(
                    client,
                    cloud_file_id=str(upload.cloud_file_id),
                    dest=dest,
                )
                part_paths.append(dest)
                downloaded.append(
                    {
                        "part_index": part_index,
                        "source": "cloud",
                        "path": str(dest),
                        "cloud_file_id": upload.cloud_file_id,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "part_index": part_index,
                        "error": "cloud_download_failed",
                        "detail": str(exc),
                    }
                )

    if use_cloud:
        factory = client_factory or AliyunDriveClient.open
        with factory(token_path) as client:
            _download_parts(client)
    else:
        _download_parts(None)

    payload: dict[str, Any] = {
        "ok": len(errors) == 0 and len(downloaded) == len(part_indices),
        "command": "live download",
        "session_id": session_id,
        "session_dir": str(session_dir),
        "output_dir": str(out_dir),
        "keep_local": keep_local,
        "parts_requested": part_indices,
        "parts_downloaded": len(downloaded),
        "downloads": downloaded,
    }
    if errors:
        payload["errors"] = errors
    if temp_dir is not None:
        payload["temp_dir"] = str(temp_dir)

    if not merge or not part_paths:
        if not payload["ok"]:
            payload["ok"] = False
        return payload

    merge_sources: list[Path] = []
    init_path = session_dir / "init.mp4"
    if init_path.is_file():
        if keep_local:
            merge_sources.append(init_path)
        else:
            init_dest = out_dir / "init.mp4"
            if not init_dest.is_file():
                shutil.copy2(init_path, init_dest)
            merge_sources.append(init_dest)
    merge_sources.extend(part_paths)

    merged_name = f"{session_dir.name}.mp4"
    merged_path = out_dir / merged_name if keep_local else out_dir / merged_name

    try:
        concat_to_mp4(
            ffmpeg=cfg.live.ffmpeg_path,
            sources=merge_sources,
            dst=merged_path,
        )
        payload["merged_path"] = str(merged_path)
        payload["merge"] = True
        if not keep_local:
            for part_path in part_paths:
                if part_path != merged_path and part_path.is_file():
                    part_path.unlink(missing_ok=True)
            init_copy = out_dir / "init.mp4"
            if init_copy.is_file() and init_path != init_copy:
                init_copy.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        payload["ok"] = False
        payload["merge"] = False
        payload["merge_error"] = str(exc)

    return payload
