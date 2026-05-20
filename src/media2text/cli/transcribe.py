from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.transcribe.whisper import WhisperBackend, whisper_backend_from_config, write_transcript_outputs
from media2text.core.workspace import open_db

app = typer.Typer(help="Transcribe media")


def _backend(cfg: AppConfig) -> WhisperBackend:
    if cfg.transcribe.engine != "whisper":
        raise typer.BadParameter(f"Unsupported engine: {cfg.transcribe.engine}")
    return whisper_backend_from_config(cfg)


@app.command("run")
def run(
    path: Path = typer.Argument(..., help="Media file or directory"),
    creator_id: str | None = typer.Option(None, "--creator"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    backend = _backend(cfg)
    conn = open_db(cfg)
    awemes = AwemeRepo(conn)
    transcribed = 0
    errors: list[dict] = []

    targets: list[Path] = []
    if path.is_dir():
        targets = sorted(path.glob("**/*.mp4"))
    else:
        targets = [path]

    if creator_id and not targets:
        for row in awemes.list_downloaded_without_transcript(creator_id=creator_id):
            if row.local_path:
                targets.append(Path(row.local_path))

    for media in targets:
        try:
            result = backend.transcribe(media, language=cfg.transcribe.language)
            json_path, _md = write_transcript_outputs(media, result)
            row = conn.execute(
                "SELECT aweme_id FROM awemes WHERE local_path = ?",
                (str(media),),
            ).fetchone()
            if row:
                awemes.mark_transcribed(row["aweme_id"], transcript_path=str(json_path))
            transcribed += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(media), "error": str(exc)})

    if creator_id:
        creator = CreatorRepo(conn).get(creator_id)
        if creator:
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=cfg.ensure_workspace())

    payload = {
        "ok": not errors,
        "command": "transcribe run",
        "transcribed": transcribed,
        "errors": errors,
    }
    emit(payload, as_json=json_out)
    if errors:
        raise typer.Exit(4)
