import typer

from media2text.core.config import AppConfig
from media2text.core.errors import ParseFailed
from media2text.core.json_out import emit
from media2text.core.manifest import refresh_manifest
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.vod import sync_creator
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.platform.profile import (
    is_profile_stale,
    platform_session_ready,
    sync_creator_profile,
)
from media2text.core.platform.bilibili.resolver import resolve_mid
from media2text.core.platform.douyin.resolver import resolve_sec_uid
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Creator registry")


def _creator_list_item(row, *, stale_days: int) -> dict:
    return {
        "id": row.id,
        "platform": row.platform,
        "sec_uid": row.sec_uid,
        "display_name": row.display_name,
        "unique_id": row.unique_id,
        "profile_url": row.profile_url,
        "monitor_enabled": bool(row.monitor_enabled),
        "profile_stale": is_profile_stale(
            display_name=row.display_name,
            profile_synced_at=row.profile_synced_at,
            stale_days=stale_days,
        ),
    }


@app.command("add")
def add(
    url: str = typer.Argument(..., help="Creator profile URL (Douyin or Bilibili space)"),
    platform: str = typer.Option("douyin", "--platform"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    plat = platform.strip().lower()
    if plat not in ("douyin", "bilibili"):
        raise typer.BadParameter("platform must be douyin or bilibili")

    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    client = None
    session = session_path(ws)
    if plat == "douyin" and session.is_file():
        client = client_from_storage(session)

    try:
        if plat == "bilibili":
            sec_uid = resolve_mid(url)
        else:
            sec_uid = resolve_sec_uid(url, client)
    except ParseFailed as exc:
        emit(
            {"ok": False, "command": "creator add", "platform": plat, "error": str(exc)},
            as_json=json_out,
        )
        raise typer.Exit(3) from exc

    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    existing = repo.get_by_sec_uid(sec_uid, platform=plat)
    if existing:
        emit(
            {
                "ok": True,
                "command": "creator add",
                "platform": plat,
                "creator_id": existing.id,
                "sec_uid": sec_uid,
                "already_exists": True,
                "monitor_enabled": bool(existing.monitor_enabled),
            },
            as_json=json_out,
        )
        return

    creator_id = repo.add(
        sec_uid=sec_uid,
        profile_url=url,
        platform=plat,
        monitor_enabled=False,
    )
    profile_result: dict | None = None
    if platform_session_ready(cfg, plat):
        profile_result = sync_creator_profile(cfg, creator_id)

    row = repo.get(creator_id)
    emit(
        {
            "ok": True,
            "command": "creator add",
            "platform": plat,
            "creator_id": creator_id,
            "sec_uid": sec_uid,
            "monitor_enabled": False,
            "display_name": row.display_name if row else None,
            "unique_id": row.unique_id if row else None,
            "profile_synced": bool(profile_result and profile_result.get("ok")),
            "profile_error": (
                profile_result.get("error")
                if profile_result and not profile_result.get("ok")
                else None
            ),
            "auth_required": bool(profile_result and profile_result.get("auth_required")),
        },
        as_json=json_out,
    )


@app.command("list")
def list_creators(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    stale_days = cfg.monitor.profile_stale_days
    items = [_creator_list_item(r, stale_days=stale_days) for r in repo.list_all()]
    emit({"ok": True, "command": "creator list", "creators": items}, as_json=json_out)


@app.command("show")
def show(
    creator_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    row = creators.get(creator_id)
    if not row:
        emit(
            {"ok": False, "command": "creator show", "error": "creator not found"},
            as_json=json_out,
        )
        raise typer.Exit(1)
    stale_days = cfg.monitor.profile_stale_days
    payload = _creator_list_item(row, stale_days=stale_days)
    payload.update(
        {
            "avatar_url": row.avatar_url,
            "signature": row.signature,
            "follower_count": row.follower_count,
            "profile_synced_at": row.profile_synced_at,
            "aweme_count": creators.count_awemes(creator_id),
            "pending_download_count": creators.count_pending_download(creator_id),
        }
    )
    emit({"ok": True, "command": "creator show", "creator": payload}, as_json=json_out)


@app.command("refresh")
def refresh(
    creator_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    result = sync_creator_profile(cfg, creator_id)
    emit({"command": "creator refresh", **result}, as_json=json_out)
    if not result.get("ok"):
        raise typer.Exit(2 if result.get("auth_required") else 1)


@app.command("monitor")
def monitor_cmd(
    creator_id: str = typer.Argument(...),
    off: bool = typer.Option(False, "--off", help="Disable monitoring"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    if not repo.get(creator_id):
        emit(
            {"ok": False, "command": "creator monitor", "error": "creator not found"},
            as_json=json_out,
        )
        raise typer.Exit(1)
    enabled = not off
    repo.set_monitor_enabled(creator_id, enabled=enabled)
    emit(
        {
            "ok": True,
            "command": "creator monitor",
            "creator_id": creator_id,
            "monitor_enabled": enabled,
        },
        as_json=json_out,
    )


@app.command("sync-dynamics")
def sync_dynamics(
    creator_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    from media2text.core.platform.bilibili.dynamic import sync_creator_dynamics

    cfg = AppConfig.load()
    result = sync_creator_dynamics(cfg, creator_id)
    emit({"command": "creator sync-dynamics", **result}, as_json=json_out)
    from media2text.core.cli_exit import raise_for_result

    raise_for_result(result)


@app.command("sync")
def sync(
    creator_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    result = sync_creator(cfg, creator_id)
    if result.get("ok"):
        conn = open_db(cfg)
        creator = CreatorRepo(conn).get(creator_id)
        if creator:
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace())
    emit({"command": "creator sync", **result}, as_json=json_out)
    from media2text.core.cli_exit import raise_for_result

    raise_for_result(result)


@app.command("remove")
def remove(
    creator_id: str = typer.Argument(...),
    delete_media: bool = typer.Option(
        False,
        "--delete-media",
        help="Remove data/creators/{sec_uid}/ for this creator",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    import shutil

    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creator = repo.get(creator_id)
    sec_uid = creator.sec_uid if creator else None
    ok = repo.remove(creator_id)
    deleted_media = False
    if ok and delete_media and sec_uid:
        media_dir = cfg.ensure_workspace() / "creators" / sec_uid
        if media_dir.is_dir():
            shutil.rmtree(media_dir)
            deleted_media = True
    emit(
        {
            "ok": ok,
            "command": "creator remove",
            "creator_id": creator_id,
            "delete_media": delete_media,
            "deleted_media": deleted_media,
        },
        as_json=json_out,
    )
    if not ok:
        raise typer.Exit(1)
