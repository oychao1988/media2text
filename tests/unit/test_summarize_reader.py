from pathlib import Path

import pytest

from media2text.core.summarize.errors import SummarizeError
from media2text.core.summarize.reader import load_content_md, load_transcript

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "summarize"


def test_load_transcript_json(tmp_path: Path) -> None:
    p = tmp_path / "a.transcript.json"
    p.write_text((FIXTURES / "short_live.json").read_text(), encoding="utf-8")
    doc = load_transcript(p)
    assert len(doc.segments) == 2
    assert doc.segments[0].text == "大家好"


def test_load_transcript_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(SummarizeError, match="not found"):
        load_transcript(tmp_path / "missing.transcript.json")


def test_load_content_md(tmp_path: Path) -> None:
    md = tmp_path / "content.md"
    md.write_text("# 动态\n\n正文", encoding="utf-8")
    doc = load_content_md(md)
    assert "正文" in doc.plain_text
