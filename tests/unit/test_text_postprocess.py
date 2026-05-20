from media2text.core.transcribe.base import TranscriptResult, TranscriptSegment
from media2text.core.transcribe.text_postprocess import (
    normalize_cjk_spacing,
    postprocess_transcript_result,
    text_with_sentence_breaks,
)


def test_normalize_cjk_spacing() -> None:
    assert normalize_cjk_spacing("一定是 我们 作为 交易 者") == "一定是我们作为交易者"
    assert normalize_cjk_spacing("hello 世界 test") == "hello 世界 test"


def test_text_with_sentence_breaks() -> None:
    raw = "第一句。第二句！第三句？"
    assert text_with_sentence_breaks(raw, normalize=False) == "第一句。\n第二句！\n第三句？"


def test_postprocess_transcript_result_segments_and_text() -> None:
    result = TranscriptResult(
        text="你好 世界。再见 朋友。",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="你好 世界"),
            TranscriptSegment(start=1.0, end=2.0, text="再见 朋友"),
        ],
        engine="deepgram",
        model="nova-3",
    )
    out = postprocess_transcript_result(
        result,
        normalize_segments=True,
        sentence_lines=True,
    )
    assert out.segments[0].text == "你好世界"
    assert out.segments[1].text == "再见朋友"
    assert out.text == "你好世界\n再见朋友"


def test_postprocess_splits_sentence_inside_utterance() -> None:
    result = TranscriptResult(
        text="unused",
        segments=[TranscriptSegment(start=0.0, end=5.0, text="第一句。第二句")],
        engine="deepgram",
        model="nova-3",
    )
    out = postprocess_transcript_result(
        result,
        normalize_segments=False,
        sentence_lines=True,
    )
    assert out.segments[0].text == "第一句。\n第二句"
    assert out.text == "第一句。\n第二句"
