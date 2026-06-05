from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.catalog import build_adapter
from media2text.core.platform.douyin.parse import infer_image_extension
from media2text.core.platform.douyin.ytdlp_fallback import download_via_ytdlp, ytdlp_available
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db

_DOWNLOAD_HEADERS = {
    "Referer": "https://www.douyin.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def _stream_to_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client, client.stream(
        "GET",
        url,
        follow_redirects=True,
        headers=_DOWNLOAD_HEADERS,
    ) as response:
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)


def _parse_media_urls(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return [str(u) for u in parsed if u]
    return None


def _download_gallery(
    *,
    adapter,
    aweme_id: str,
    dest_dir: Path,
    media_urls: list[str] | None,
) -> tuple[str, bool, str | None]:
    errors: list[str] = []
    urls = media_urls
    if not urls:
        try:
            urls = adapter.resolve_gallery_urls(aweme_id=aweme_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            urls = None

    if not urls:
        return aweme_id, False, "; ".join(errors) if errors else "no gallery urls"

    dest_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for index, url in enumerate(urls, start=1):
        ext = infer_image_extension(url)
        target = dest_dir / f"{index:02d}{ext}"
        try:
            _stream_to_file(url, target)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"image {index}: {exc}")

    if saved == 0:
        return aweme_id, False, "; ".join(errors) if errors else "gallery download failed"
    return aweme_id, True, str(dest_dir)


def _download_one(
    *,
    adapter,
    aweme_id: str,
    dest: Path,
    session_file: Path | None,
    download_url: str | None = None,
    media_type: str = "video",
    media_urls: list[str] | None = None,
) -> tuple[str, bool, str | None]:
    if media_type == "gallery":
        return _download_gallery(
            adapter=adapter,
            aweme_id=aweme_id,
            dest_dir=dest,
            media_urls=media_urls,
        )

    errors: list[str] = []

    if download_url:
        try:
            _stream_to_file(download_url, dest)
            return aweme_id, True, str(dest)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cached url: {exc}")

    try:
        url = adapter.resolve_download_url(aweme_id=aweme_id)
        _stream_to_file(url, dest)
        return aweme_id, True, str(dest)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    if session_file and session_file.is_file() and ytdlp_available():
        try:
            download_via_ytdlp(aweme_id=aweme_id, dest=dest, session_file=session_file)
            return aweme_id, True, str(dest)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"yt-dlp: {exc}")

    return aweme_id, False, "; ".join(errors) if errors else "unknown"


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
            media_type = row.media_type or "video"
            if media_type == "gallery":
                dest = ws / "creators" / creator.sec_uid / "images" / row.aweme_id
            else:
                dest = ws / "creators" / creator.sec_uid / "videos" / f"{row.aweme_id}.mp4"
            futures.append(
                pool.submit(
                    _download_one,
                    adapter=adapter,
                    aweme_id=row.aweme_id,
                    dest=dest,
                    session_file=session_file,
                    download_url=row.download_url,
                    media_type=media_type,
                    media_urls=_parse_media_urls(row.media_urls),
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
