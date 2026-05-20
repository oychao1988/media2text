import typer

from media2text.core.config import AppConfig
from media2text.core.errors import ParseFailed
from media2text.core.json_out import emit
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.platform.douyin.resolver import resolve_sec_uid
from media2text.core.manifest import refresh_manifest
from media2text.core.platform.douyin.catalog import sync_creator
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Creator registry")


@app.command("add")
def add(
    url: str = typer.Argument(..., help="Douyin profile URL"),
    watch_live: bool = typer.Option(True, "--watch-live/--no-watch-live"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    client = None
    session = session_path(ws)
    if session.is_file():
        client = client_from_storage(session)
    try:
        sec_uid = resolve_sec_uid(url, client)
    except ParseFailed as exc:
        emit({"ok": False, "command": "creator add", "error": str(exc)}, as_json=json_out)
        raise typer.Exit(3) from exc

    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    existing = repo.get_by_sec_uid(sec_uid)
    if existing:
        emit(
            {
                "ok": True,
                "command": "creator add",
                "creator_id": existing.id,
                "sec_uid": sec_uid,
                "already_exists": True,
            },
            as_json=json_out,
        )
        return

    creator_id = repo.add(sec_uid=sec_uid, profile_url=url, watch_live=watch_live)
    emit(
        {
            "ok": True,
            "command": "creator add",
            "creator_id": creator_id,
            "sec_uid": sec_uid,
            "watch_live": watch_live,
        },
        as_json=json_out,
    )


@app.command("list")
def list_creators(json_out: bool = typer.Option(False, "--json")) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    items = [
        {
            "id": r.id,
            "sec_uid": r.sec_uid,
            "display_name": r.display_name,
            "profile_url": r.profile_url,
            "watch_live": bool(r.watch_live),
        }
        for r in repo.list_all()
    ]
    emit({"ok": True, "command": "creator list", "creators": items}, as_json=json_out)


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
    if not result.get("ok"):
        raise typer.Exit(1)


@app.command("remove")
def remove(
    creator_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    ok = repo.remove(creator_id)
    emit({"ok": ok, "command": "creator remove", "creator_id": creator_id}, as_json=json_out)
    if not ok:
        raise typer.Exit(1)
