from __future__ import annotations

from media2text.core.summarize.reader import TranscriptSegment


def _segment_line(seg: TranscriptSegment) -> str:
    return f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text}"


def chunk_segments(
    segments: list[TranscriptSegment],
    *,
    max_chars: int,
    max_minutes: float,
) -> list[list[TranscriptSegment]]:
    if not segments:
        return []
    max_span_sec = max_minutes * 60.0
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0
    chunk_start = segments[0].start

    for seg in segments:
        line = _segment_line(seg)
        line_len = len(line) + 1
        span = seg.end - chunk_start
        would_exceed_chars = current and current_chars + line_len > max_chars
        would_exceed_time = current and span > max_span_sec

        if would_exceed_chars or would_exceed_time:
            chunks.append(current)
            current = []
            current_chars = 0
            chunk_start = seg.start

        current.append(seg)
        current_chars += line_len

    if current:
        chunks.append(current)
    return chunks


def format_chunk(segments: list[TranscriptSegment]) -> str:
    return "\n".join(_segment_line(s) for s in segments)


def chunk_plain_text(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        parts.append(text[start : start + max_chars])
        start += max_chars
    return parts
