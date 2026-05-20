from __future__ import annotations

import re

from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment

# Han + extension blocks; collapse spaces only between CJK chars (keep Latin/digit gaps).
_CJK_CHAR = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"
_CJK_INTER_SPACE = re.compile(rf"(?<=({_CJK_CHAR}))\s+(?={_CJK_CHAR})")

# Insert newline after Chinese sentence-ending punctuation when more text follows.
_SENTENCE_BREAK = re.compile(r"(?<=[。！？；…])(?=[^\s。！？；…\n])")


def normalize_cjk_spacing(text: str) -> str:
    """Remove tokenization spaces between CJK characters (e.g. Deepgram utterances)."""
    if not text:
        return text
    prev = None
    out = text
    while prev != out:
        prev = out
        out = _CJK_INTER_SPACE.sub("", out)
    return out.strip()


def text_with_sentence_breaks(text: str, *, normalize: bool = True) -> str:
    """One sentence per line in `text` (JSON field), using 。！？；… boundaries."""
    if normalize:
        text = normalize_cjk_spacing(text)
    text = text.strip()
    if not text:
        return text
    return _SENTENCE_BREAK.sub("\n", text)


def _format_text_block(text: str, *, normalize: bool, sentence_lines: bool) -> str:
    if normalize:
        text = normalize_cjk_spacing(text)
    if sentence_lines and text:
        text = text_with_sentence_breaks(text, normalize=False)
    return text


def postprocess_transcript_result(
    result: TranscriptResult,
    *,
    normalize_segments: bool,
    sentence_lines: bool,
) -> TranscriptResult:
    """Normalize segment text; build `text` with line breaks between utterances and sentences."""
    segments: list[TranscriptSegment] = []
    for seg in result.segments:
        text = _format_text_block(
            seg.text,
            normalize=normalize_segments,
            sentence_lines=sentence_lines,
        )
        segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))

    if segments:
        full_text = "\n".join(s.text for s in segments if s.text)
    else:
        full_text = _format_text_block(
            result.text,
            normalize=normalize_segments,
            sentence_lines=sentence_lines,
        )

    return TranscriptResult(
        text=full_text,
        segments=segments,
        engine=result.engine,
        model=result.model,
    )
