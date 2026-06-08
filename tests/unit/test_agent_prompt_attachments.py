"""Prompt builder attachment block tests."""

from __future__ import annotations

from media2text.agent.prompt_builder import build_system_prompt
from media2text.core.config import AppConfig


def test_prompt_includes_attachments_from_binding() -> None:
    cfg = AppConfig.load()
    parts = build_system_prompt(
        cfg=cfg,
        thread={
            "creator_id": None,
            "binding": {
                "context_mode": "both",
                "attachments": [
                    {
                        "id": "transcript:creators/a/live/x.transcript.json",
                        "docType": "transcript",
                        "path": "creators/a/live/x.transcript.json",
                        "label": "直播场次",
                        "creatorName": "博主A",
                    },
                    {
                        "id": "summary:creators/a/live/x.summary.md",
                        "docType": "summary",
                        "path": "creators/a/live/x.summary.md",
                        "label": "摘要",
                        "creatorName": "博主A",
                    },
                ],
            },
        },
    )
    assert "附加文档:" in parts.context
    assert "creators/a/live/x.transcript.json" in parts.context
    assert "creators/a/live/x.summary.md" in parts.context


def test_prompt_filters_attachments_by_context_mode() -> None:
    cfg = AppConfig.load()
    parts = build_system_prompt(
        cfg=cfg,
        thread={
            "creator_id": None,
            "binding": {
                "context_mode": "transcript",
                "attachments": [
                    {
                        "docType": "transcript",
                        "path": "a.transcript.json",
                        "label": "转写",
                    },
                    {
                        "docType": "summary",
                        "path": "a.summary.md",
                        "label": "摘要",
                    },
                ],
            },
        },
    )
    assert "a.transcript.json" in parts.context
    assert "a.summary.md" not in parts.context


def test_prompt_migrates_legacy_paths_to_attachments_block() -> None:
    cfg = AppConfig.load()
    parts = build_system_prompt(
        cfg=cfg,
        thread={
            "creator_id": None,
            "binding": {
                "context_mode": "both",
                "transcript_path": "creators/x/live/old.transcript.json",
                "summary_path": "creators/x/live/old.summary.md",
                "session_kind": "live",
                "session_id": "sess-1",
            },
        },
    )
    assert "附加文档:" in parts.context
    assert "old.transcript.json" in parts.context
    assert "old.summary.md" in parts.context
