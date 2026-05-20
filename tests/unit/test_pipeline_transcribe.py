from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, TranscribeConfig
from media2text.core.pipeline.runner import run_pipeline
from media2text.core.storage.repos import CreatorRepo
from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.workspace import open_db


def test_pipeline_openai_transcribes_downloaded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", transcribe=TranscribeConfig(engine="openai"))
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="MS4wLjABAAAApipe", profile_url="https://example.com")
    media = tmp_path / "data" / "creators" / "MS4wLjABAAAApipe" / "vod" / "a.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"video")
    aweme_id = "7123456789012345678"
    now = "2026-05-20T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO awemes
          (aweme_id, creator_id, title, create_time, media_type, sync_status, local_path, updated_at)
        VALUES (?, ?, 't', ?, 'video', 'downloaded', ?, ?)
        """,
        (aweme_id, cid, now, str(media), now),
    )
    conn.commit()

    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = TranscriptResult(
        text="done",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="done")],
        engine="openai",
        model="whisper-1",
    )

    with (
        patch("media2text.core.pipeline.runner.sync_creator", return_value={"ok": True}),
        patch(
            "media2text.core.pipeline.runner.download_pending",
            return_value={"ok": True, "downloaded": 0, "errors": []},
        ),
        patch(
            "media2text.core.pipeline.runner.transcribe_engine_available",
            return_value=(True, None),
        ),
        patch(
            "media2text.core.pipeline.runner.create_transcribe_backend",
            return_value=mock_backend,
        ),
        patch("media2text.core.pipeline.runner.refresh_manifest"),
    ):
        outcome = run_pipeline(cfg, creator_id=cid)

    assert outcome["transcribed"] == 1
    assert media.with_suffix(".transcript.json").is_file()
    row = conn.execute(
        "SELECT transcribe_status FROM awemes WHERE aweme_id = ?",
        (aweme_id,),
    ).fetchone()
    assert row is not None
    assert row["transcribe_status"] == "done"
    mock_backend.transcribe.assert_called_once()
