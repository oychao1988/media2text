from __future__ import annotations

from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.platform.douyin.catalog import sync_creator
from media2text.core.platform.douyin.download import download_pending
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.transcribe.whisper import WhisperBackend, write_transcript_outputs
from media2text.core.workspace import open_db


def run_pipeline(cfg: AppConfig, *, creator_id: str) -> dict:
    conn = open_db(cfg)
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}

    errors: list[dict] = []
    sync_result = sync_creator(cfg, creator_id)
    download_result = download_pending(cfg, creator_id=creator_id)
    if download_result.get("errors"):
        errors.extend(download_result["errors"])

    transcribed = 0
    if cfg.transcribe.engine == "whisper":
        backend = WhisperBackend(
            model=cfg.transcribe.whisper.model,
            device=cfg.transcribe.whisper.device,
        )
        awemes = AwemeRepo(conn)
        for row in awemes.list_downloaded_without_transcript(creator_id=creator_id):
            if not row.local_path:
                continue
            media = Path(row.local_path)
            try:
                result = backend.transcribe(media, language=cfg.transcribe.language)
                json_path, _ = write_transcript_outputs(media, result)
                awemes.mark_transcribed(row.aweme_id, transcript_path=str(json_path))
                transcribed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"aweme_id": row.aweme_id, "error": str(exc)})

    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace())

    return {
        "ok": sync_result.get("ok", False) and download_result.get("ok", False) and not errors,
        "command": "pipeline run",
        "sync": sync_result,
        "download": download_result,
        "transcribed": transcribed,
        "errors": errors,
        "auth_required": False,
    }
