from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.catalog import build_adapter
from media2text.core.platform.douyin.ytdlp_fallback import download_via_ytdlp, ytdlp_available
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def _download_one(
    *,
    adapter,
    aweme_id: str,
    dest: Path,
    session_file: Path | None,
) -> tuple[str, bool, str | None]:
    primary_error: str | None = None
    try:
        url = adapter.resolve_download_url(aweme_id=aweme_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client, client.stream(
            "GET", url, follow_redirects=True
        ) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
        return aweme_id, True, str(dest)
    except Exception as exc:  # noqa: BLE001
        primary_error = str(exc)

    if session_file and session_file.is_file() and ytdlp_available():
        try:
            download_via_ytdlp(aweme_id=aweme_id, dest=dest, session_file=session_file)
            return aweme_id, True, str(dest)
        except Exception as exc:  # noqa: BLE001
            return aweme_id, False, f"{primary_error}; yt-dlp: {exc}"

    return aweme_id, False, primary_error


def download_pending(
    cfg: AppConfig,
    *,
    creator_id: str | None = None,
    limit: int | None = None,
) -> dict:
    conn = open_db(cfg)
    awemes = AwemeRepo(conn)
    creators = CreatorRepo(conn)
    adapter = build_adapter(cfg)
    ws = cfg.ensure_workspace()
    session_file = session_path(ws)
    if not session_file.is_file():
        session_file = None

    pending = awemes.list_pending_download(
        creator_id=creator_id,
        monitor_only=creator_id is None,
    )
    if limit is not None and limit > 0:
        pending = pending[:limit]
    if not pending:
        return {"ok": True, "downloaded": 0, "failed": 0, "errors": []}

    downloaded = 0
    failed = 0
    errors: list[dict] = []
    concurrency = cfg.platforms.douyin.download_concurrency

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for row in pending:
            creator = creators.get(row.creator_id)
            if not creator:
                continue
            dest = ws / "creators" / creator.sec_uid / "videos" / f"{row.aweme_id}.mp4"
            futures.append(
                pool.submit(
                    _download_one,
                    adapter=adapter,
                    aweme_id=row.aweme_id,
                    dest=dest,
                    session_file=session_file,
                )
            )
        for future in as_completed(futures):
            aweme_id, ok, result = future.result()
            if ok:
                awemes.mark_downloaded(aweme_id, local_path=result)
                downloaded += 1
            else:
                awemes.mark_failed(aweme_id, error=result or "unknown")
                failed += 1
                errors.append({"aweme_id": aweme_id, "error": result})

    return {"ok": failed == 0, "downloaded": downloaded, "failed": failed, "errors": errors}
