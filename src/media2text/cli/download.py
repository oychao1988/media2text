import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.manifest import refresh_manifest
from media2text.core.platform.vod import download_pending
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Download videos")


@app.command("run")
def run(
    creator_id: str | None = typer.Option(None, "--creator"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    result = download_pending(cfg, creator_id=creator_id, limit=limit)
    if creator_id:
        conn = open_db(cfg)
        creator = CreatorRepo(conn).get(creator_id)
        if creator:
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace())
    emit({"ok": result["ok"], "command": "download run", **result}, as_json=json_out)
    from media2text.core.cli_exit import raise_for_result

    raise_for_result(result)
