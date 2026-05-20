from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.storage.repos import AwemeRepo, CreatorRepo


def _transcript_sidecar_path(media_path: str | None) -> str | None:
    if not media_path:
        return None
    json_path = Path(media_path).with_suffix(".transcript.json")
    return str(json_path) if json_path.is_file() else None


def refresh_manifest(conn, *, sec_uid: str, workspace: Path) -> Path:
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)

    creator = next((c for c in creators.list_all() if c.sec_uid == sec_uid), None)
    if not creator:
        raise ValueError(f"creator not found for sec_uid={sec_uid}")

    items: list[dict] = []
    for row in awemes.list_for_creator(creator.id):
        items.append(
            {
                "id": row.aweme_id,
                "type": "vod",
                "title": row.title,
                "media_path": row.local_path,
                "transcript_path": row.transcript_path,
                "status": row.sync_status if row.transcribe_status != "done" else "transcribed",
            }
        )

    live_rows = conn.execute(
        "SELECT * FROM live_sessions WHERE creator_id = ? ORDER BY started_at DESC",
        (creator.id,),
    ).fetchall()
    for row in live_rows:
        data = dict(row)
        local_path = data.get("local_path")
        items.append(
            {
                "id": data["id"],
                "type": "live",
                "title": None,
                "media_path": local_path,
                "transcript_path": _transcript_sidecar_path(local_path),
                "status": data.get("status"),
            }
        )

    payload = {
        "sec_uid": sec_uid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    out_dir = workspace / "creators" / sec_uid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "agent-manifest.json"
    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_path)
    return out_path
