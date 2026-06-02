import json
from pathlib import Path

from media2text.core.summarize.base import DISCLAIMER_MD, SummaryResult
from media2text.core.summarize.writer import write_summary


def test_write_summary_sidecars(tmp_path: Path) -> None:
    media = tmp_path / "20260601T130643Z.mp4"
    media.touch()
    result = SummaryResult(
        engine="openai",
        model="deepseek-ai/deepseek-v4-pro",
        profile="live_market_recap",
        markdown="## 核心观点\n- foo",
        chunks=2,
        provider_base_url="https://integrate.api.nvidia.com/v1",
        llm_usage={
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "requests": 2,
        },
    )
    md_path, json_path = write_summary(
        media, result, source_transcript=media.with_suffix(".transcript.json")
    )
    text = md_path.read_text(encoding="utf-8")
    assert DISCLAIMER_MD.split("\n")[0] in text
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    assert meta["profile"] == "live_market_recap"
    assert meta["llm_usage"]["total_tokens"] == 1200
    assert "sections" not in meta
