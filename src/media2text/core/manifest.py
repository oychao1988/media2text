from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.storage.repos import AwemeRepo, CreatorRepo, DynamicRepo


def _transcript_sidecar_path(media_path: str | None) -> str | None:
    if not media_path:
        return None
    json_path = Path(media_path).with_suffix(".transcript.json")
    return str(json_path) if json_path.is_file() else None


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
        live_items.append(
            {
                "id": data["id"],
                "type": "live",
                "title": None,
                "media_path": local_path,
                "transcript_path": _transcript_sidecar_path(local_path),
                "status": data.get("status"),
            }
        )

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

    out_dir = workspace / "creators" / sec_uid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "agent-manifest.json"
    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_path)
    return out_path
