from media2text.core.summarize.chunker import chunk_segments
from media2text.core.summarize.reader import TranscriptSegment


def test_single_chunk_short_text() -> None:
    segs = [TranscriptSegment(0, 10, "a" * 100)]
    chunks = chunk_segments(segs, max_chars=24000, max_minutes=30)
    assert len(chunks) == 1


def test_splits_when_char_budget_exceeded() -> None:
    segs = [
        TranscriptSegment(0, 60, "x" * 15000),
        TranscriptSegment(60, 120, "y" * 15000),
    ]
    chunks = chunk_segments(segs, max_chars=20000, max_minutes=999)
    assert len(chunks) == 2
