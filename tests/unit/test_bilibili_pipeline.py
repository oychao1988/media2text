from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.pipeline.runner import run_pipeline
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_pipeline_bilibili_transcribe_skipped_without_engine(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="777",
        profile_url="https://space.bilibili.com/777",
        platform="bilibili",
    )
    with (
        patch(
            "media2text.core.pipeline.runner.download_pending",
            return_value={"ok": True, "downloaded": 0, "failed": 0, "errors": []},
        ),
        patch(
            "media2text.core.pipeline.runner.transcribe_engine_available",
            return_value=(False, "whisper extra not installed"),
        ),
    ):
        result = run_pipeline(cfg, creator_id=cid)
    assert result["sync"]["ok"] is True
    assert result["sync"]["new_count"] == 3
    assert result.get("transcribe_skipped") is True
    assert "whisper" in (result.get("transcribe_skip_reason") or "").lower()
