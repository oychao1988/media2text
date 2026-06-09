from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, DynamicRepo


def _transcript_sidecar_path(media_path: str | None) -> str | None:
    if not media_path:
        return None
    json_path = Path(media_path).with_suffix(".transcript.json")
    return str(json_path) if json_path.is_file() else None


def _summary_sidecar_path(media_path: str | None) -> str | None:
    if not media_path:
        return None
    p = Path(media_path)
    if p.name == "content.md":
        summary = p.with_name("content.summary.md")
    else:
        summary = p.with_suffix(".summary.md")
    return str(summary) if summary.is_file() else None


def _playback_mode_from_path(local_path: str | None) -> str:
    if not local_path:
        return "flv"
    p = Path(local_path)
    if p.suffix.lower() == ".m3u8" or p.name == "master.m3u8":
        return "hls"
    return "flv"


def _live_parts_summary(conn, session_id: str) -> list[dict]:
    parts = SegmentManifestRepo(conn).list_parts(session_id)
    summary: list[dict] = []
    for part in parts:
        entry: dict = {
            "index": part.part_index,
            "state": part.state,
        }
        if part.cloud_path:
            entry["cloud_path"] = part.cloud_path
        summary.append(entry)
    return summary


def _discover_live_groups(live_dir: Path) -> list[dict]:
    groups: list[dict] = []
    if not live_dir.is_dir():
        return groups
    for md in sorted(live_dir.glob("*_merged.summary.md")):
        stem = md.name.replace("_merged.summary.md", "")
        if len(stem) != 8 or not stem.isdigit():
            continue
        iso_date = f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}"
        entry: dict = {
            "date": iso_date,
            "summary_path": str(md),
            "session_ids": [],
        }
        json_path = md.with_name(md.name.replace(".summary.md", ".summary.json"))
        if json_path.is_file():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                entry["session_ids"] = [
                    s.get("session_id")
                    for s in data.get("sources") or []
                    if s.get("session_id")
                ]
            except (OSError, json.JSONDecodeError):
                pass
        groups.append(entry)
    return groups


def _dynamic_manifest_entry(workspace: Path, sec_uid: str, row) -> dict:
    rel_dir = row.local_dir or f"dynamics/{row.dynamic_id}"
    rel_path = Path(rel_dir)
    base = workspace / "creators" / sec_uid / rel_path
    content_md = base / "content.md"
    images: list[str] = []
    images_dir = base / "images"
    if images_dir.is_dir():
        images = sorted(
            str((rel_path / "images" / p.name).as_posix())
            for p in images_dir.iterdir()
            if p.is_file()
        )
    entry: dict = {
        "dynamic_id": row.dynamic_id,
        "type": row.dynamic_type,
        "path": rel_dir.replace("\\", "/"),
        "status": row.sync_status,
        "published_at": row.published_at,
        "image_count": row.image_count,
    }
    if content_md.is_file():
        entry["content_md"] = f"{rel_dir}/content.md".replace("\\", "/")
    if images:
        entry["images"] = images
    return entry


def refresh_manifest(
    conn,
    *,
    sec_uid: str,
    workspace: Path,
    platform: str | None = None,
) -> Path:
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)
    dynamics = DynamicRepo(conn)

    if platform:
        creator = creators.get_by_sec_uid(sec_uid, platform=platform)
    else:
        creator = next((c for c in creators.list_all() if c.sec_uid == sec_uid), None)
    if not creator:
        raise ValueError(f"creator not found for sec_uid={sec_uid}")

    vod_items: list[dict] = []
    for row in awemes.list_for_creator(creator.id):
        vod_items.append(
            {
                "id": row.aweme_id,
                "type": "vod",
                "title": row.title,
                "media_path": row.local_path,
                "transcript_path": row.transcript_path,
                "summary_path": _summary_sidecar_path(row.local_path),
                "status": row.sync_status if row.transcribe_status != "done" else "transcribed",
            }
        )

    live_items: list[dict] = []
    live_rows = conn.execute(
        "SELECT * FROM live_sessions WHERE creator_id = ? ORDER BY started_at DESC",
        (creator.id,),
    ).fetchall()
    for row in live_rows:
        data = dict(row)
        local_path = data.get("local_path")
        entry: dict = {
            "id": data["id"],
            "type": "live",
            "title": None,
            "media_path": local_path,
            "transcript_path": _transcript_sidecar_path(local_path),
            "summary_path": _summary_sidecar_path(local_path),
            "status": data.get("status"),
        }
        if data.get("pipeline_mode"):
            entry["pipeline_mode"] = data["pipeline_mode"]
        if data.get("transcribe_status"):
            entry["transcribe_status"] = data["transcribe_status"]
        if data.get("cloud_file_id"):
            entry["cloud_file_id"] = data["cloud_file_id"]
        if data.get("cloud_relative_path"):
            entry["cloud_relative_path"] = data["cloud_relative_path"]
        if data.get("cloud_upload_status"):
            entry["cloud_upload_status"] = data["cloud_upload_status"]
        playback_mode = _playback_mode_from_path(local_path)
        parts = _live_parts_summary(conn, data["id"])
        if parts and playback_mode == "flv":
            playback_mode = "hls"
        entry["playback_mode"] = playback_mode
        if parts:
            entry["parts"] = parts
        live_items.append(entry)

    dynamic_items: list[dict] = []
    if creator.platform == "bilibili":
        for row in dynamics.list_for_creator(creator.id):
            if row.sync_status == "synced":
                dynamic_items.append(
                    _dynamic_manifest_entry(workspace, sec_uid, row)
                )

    payload = {
        "platform": creator.platform,
        "sec_uid": sec_uid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": vod_items + live_items + dynamic_items,
        "live": live_items,
        "archives": vod_items,
    }
    if creator.platform == "bilibili":
        payload["mid"] = sec_uid
        payload["dynamics"] = dynamic_items

    live_dir = workspace / "creators" / sec_uid / "live"
    payload["live_groups"] = _discover_live_groups(live_dir)

    out_dir = workspace / "creators" / sec_uid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "agent-manifest.json"
    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_path)
    return out_path
