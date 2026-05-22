from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.bilibili.dedupe import register_bvid
from media2text.core.platform.bilibili.catalog import build_adapter
from media2text.core.platform.bilibili.models_dynamic import ParsedDynamic
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, DynamicRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()


def _extension_for_url(url: str, content_type: str | None) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return suffix
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        if ct in mapping:
            return mapping[ct]
    return ".jpg"


def _refs_json(parsed: ParsedDynamic) -> str:
    refs: dict[str, str] = {}
    if parsed.bvid:
        refs["bvid"] = parsed.bvid
    if parsed.opus_id:
        refs["opus_id"] = parsed.opus_id
    return json.dumps(refs, ensure_ascii=False)


def _local_dir_rel(dynamic_id: str) -> str:
    return f"dynamics/{dynamic_id}"


def _count_existing_images(images_dir: Path) -> int:
    if not images_dir.is_dir():
        return 0
    return sum(1 for p in images_dir.iterdir() if p.is_file())


def _download_images(
    client: httpx.Client | None,
    *,
    urls: list[str],
    images_dir: Path,
    start_index: int,
    max_total: int,
) -> int:
    images_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for offset, url in enumerate(urls):
        if start_index + offset >= max_total:
            break
        idx = start_index + offset + 1
        ext = _extension_for_url(url, None)
        dest = images_dir / f"{idx:03d}{ext}"
        if dest.is_file() and dest.stat().st_size > 0:
            downloaded += 1
            continue
        if not client:
            continue
        try:
            resp = client.get(url, follow_redirects=True, timeout=60.0)
            resp.raise_for_status()
            ext = _extension_for_url(url, resp.headers.get("content-type"))
            dest = images_dir / f"{idx:03d}{ext}"
            dest.write_bytes(resp.content)
            downloaded += 1
        except httpx.HTTPError as exc:
            log.warning("bilibili_dynamic_image_download_failed", url=url, error=str(exc))
    return downloaded


def _persist_dynamic(
    cfg: AppConfig,
    *,
    creator_id: str,
    mid: str,
    parsed: ParsedDynamic,
    dynamics: DynamicRepo,
    awemes: AwemeRepo,
    client: httpx.Client | None,
    download_images: bool,
    max_images: int,
) -> tuple[bool, int, bool]:
    """Returns (is_new, images_downloaded, bvid_registered)."""
    rel_dir = _local_dir_rel(parsed.dynamic_id)
    base = cfg.ensure_workspace() / "creators" / mid / rel_dir
    existing = dynamics.get(parsed.dynamic_id)
    is_new = existing is None
    if existing and existing.sync_status == "synced":
        return False, 0, False

    refs = _refs_json(parsed)
    dynamics.upsert_listed(
        creator_id=creator_id,
        dynamic_id=parsed.dynamic_id,
        dynamic_type=parsed.dynamic_type,
        text=parsed.text or None,
        refs_json=refs,
        local_dir=rel_dir,
        published_at=parsed.published_at,
    )

    base.mkdir(parents=True, exist_ok=True)
    content_path = base / "content.md"
    content_path.write_text(parsed.text or "", encoding="utf-8")

    bvid_new = False
    if parsed.bvid:
        bvid_new = register_bvid(
            awemes,
            creator_id=creator_id,
            bvid=parsed.bvid,
            title=parsed.text.split("\n")[0][:200] if parsed.text else None,
            create_time=parsed.pub_ts,
        )

    image_urls = list(parsed.image_urls)
    if len(image_urls) > max_images:
        image_urls = image_urls[:max_images]
        log.warning(
            "bilibili_dynamic_images_truncated",
            dynamic_id=parsed.dynamic_id,
            max_images=max_images,
        )

    images_dir = base / "images"
    start_index = 0
    if existing and existing.sync_status != "synced":
        start_index = _count_existing_images(images_dir)

    images_downloaded = 0
    if download_images and image_urls:
        if client:
            images_downloaded = _download_images(
                client,
                urls=image_urls,
                images_dir=images_dir,
                start_index=start_index,
                max_total=max_images,
            )
        else:
            images_downloaded = max(0, len(image_urls) - start_index)
    elif image_urls:
        images_downloaded = len(image_urls)

    meta = {
        "dynamic_id": parsed.dynamic_id,
        "dynamic_type": parsed.dynamic_type,
        "published_at": parsed.published_at,
        "refs": json.loads(refs),
        "image_urls": image_urls,
    }
    (base / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    dynamics.mark_synced(
        parsed.dynamic_id,
        image_count=images_downloaded if download_images else len(image_urls),
        text=parsed.text or None,
        refs_json=refs,
    )
    return is_new, images_downloaded, bvid_new


def sync_creator_dynamics(cfg: AppConfig, creator_id: str) -> dict:
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    dynamics = DynamicRepo(conn)
    awemes = AwemeRepo(conn)
    creator = creators.get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}
    if creator.platform != "bilibili":
        return {"ok": False, "error": "creator is not bilibili"}

    bcfg = cfg.platforms.bilibili
    adapter = build_adapter(cfg)
    offset = ""
    pages = 0
    new_count = 0
    images_downloaded = 0
    bvid_registered = 0
    errors: list[dict] = []

    try:
        while True:
            items, next_offset, has_more = adapter.list_dynamics(
                sec_uid=creator.sec_uid, offset=offset
            )
            hit_synced = False
            for parsed in items:
                if dynamics.is_synced(parsed.dynamic_id):
                    hit_synced = True
                    continue
                try:
                    is_new, img_n, bvid_new = _persist_dynamic(
                        cfg,
                        creator_id=creator.id,
                        mid=creator.sec_uid,
                        parsed=parsed,
                        dynamics=dynamics,
                        awemes=awemes,
                        client=getattr(adapter, "_client", None),
                        download_images=bcfg.download_dynamic_images,
                        max_images=bcfg.max_dynamic_images_per_item,
                    )
                except Exception as exc:  # noqa: BLE001
                    dynamics.mark_failed(parsed.dynamic_id, error=str(exc))
                    errors.append({"dynamic_id": parsed.dynamic_id, "error": str(exc)})
                    continue
                if is_new:
                    new_count += 1
                images_downloaded += img_n
                if bvid_new:
                    bvid_registered += 1

            pages += 1
            if hit_synced:
                break
            if not has_more or not next_offset:
                break
            if bcfg.max_dynamic_sync_pages and pages >= bcfg.max_dynamic_sync_pages:
                break
            offset = next_offset
    except AuthRequired as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": True,
            "platform_changed": False,
            "error": str(exc),
        }
    except PlatformChanged as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": False,
            "platform_changed": True,
            "error": str(exc),
        }
    except ParseFailed as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": False,
            "platform_changed": True,
            "error": str(exc),
        }

    return {
        "ok": not errors,
        "creator_id": creator_id,
        "new_count": new_count,
        "images_downloaded": images_downloaded,
        "bvid_registered": bvid_registered,
        "pages": pages,
        "errors": errors,
        "auth_required": False,
        "platform_changed": False,
        "interval_sec": bcfg.dynamic_poll_interval_sec,
    }


def run_dynamic_tick(cfg: AppConfig, *, creator_id: str | None = None) -> dict:
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    targets = [c for c in creators.list_monitored() if c.platform == "bilibili"]
    if creator_id:
        row = creators.get(creator_id)
        targets = (
            [row]
            if row and row.monitor_enabled and row.platform == "bilibili"
            else []
        )

    bcfg = cfg.platforms.bilibili
    if bcfg.dynamic_poll_interval_sec < 30:
        log.warning(
            "bilibili_dynamic_poll_interval_low",
            interval_sec=bcfg.dynamic_poll_interval_sec,
            hint="consider >= 30s to reduce rate-limit risk",
        )

    results: list[dict] = []
    errors: list[dict] = []
    auth_required = False
    platform_changed = False
    total_new = 0
    total_images = 0

    for creator in targets:
        outcome = sync_creator_dynamics(cfg, creator.id)
        if outcome.get("auth_required"):
            auth_required = True
        if outcome.get("platform_changed"):
            platform_changed = True
        if outcome.get("errors"):
            for item in outcome["errors"]:
                errors.append({"creator_id": creator.id, **item})
        total_new += int(outcome.get("new_count") or 0)
        total_images += int(outcome.get("images_downloaded") or 0)
        results.append(outcome)

    return {
        "creators": len(targets),
        "new_count": total_new,
        "images_downloaded": total_images,
        "interval_sec": bcfg.dynamic_poll_interval_sec,
        "results": results,
        "errors": errors,
        "auth_required": auth_required,
        "platform_changed": platform_changed,
    }
