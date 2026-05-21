from pathlib import Path

from media2text.core.notify.content import extract_transcript_summary


def test_extract_transcript_summary(tmp_path: Path) -> None:
    md = tmp_path / "t.md"
    md.write_text(
        "# Transcript: x.mp4\n\n"
        "- [0.0s - 1.0s] 第一句。\n"
        "- [1.0s - 2.0s] 第二句更长一点。\n",
        encoding="utf-8",
    )
    summary = extract_transcript_summary(md, max_chars=100)
    assert "第一句" in summary
    assert "第二句" in summary
    assert "[0.0s" not in summary
