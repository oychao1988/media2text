import pytest

from media2text.agent.creator_distill.tavily_client import TavilyResult, TavilySearchResponse
from media2text.agent.creator_distill.web_research import (
    WebResearchResult,
    channel_has_valid_content,
    run_six_channel_research,
)
from media2text.agent.creator_distill.web_search import NoneWebSearchProvider
from media2text.core.config import DistillConfig

pytestmark = pytest.mark.agent


def test_channel_valid_when_answer_present() -> None:
    assert channel_has_valid_content(TavilySearchResponse("ans", [])) is True


def test_channel_valid_when_results_after_denylist() -> None:
    resp = TavilySearchResponse("", [TavilyResult("t", "https://douyin.com/x", "c")])
    assert channel_has_valid_content(resp, denylist=["zhihu.com"]) is True


def test_channel_invalid_when_only_denylisted_results() -> None:
    resp = TavilySearchResponse(
        "",
        [TavilyResult("t", "https://zhihu.com/question/1", "c")],
    )
    assert channel_has_valid_content(resp, denylist=["zhihu.com"]) is False


def test_run_six_channel_writes_files(tmp_path, monkeypatch) -> None:
    refs = tmp_path / "research"
    cfg = DistillConfig(bootstrap_web_research=True, web_search_provider="tavily")

    def fake_search(self, query, **kw):
        return TavilySearchResponse(f"answer:{query[:10]}", [])

    monkeypatch.setattr(
        "media2text.agent.creator_distill.web_research.TavilyClient.search",
        fake_search,
    )
    monkeypatch.setattr(
        "media2text.agent.creator_distill.web_research.resolve_tavily_api_key",
        lambda **kw: "tvly-fake",
    )
    result = run_six_channel_research(
        cfg=cfg,
        refs_dir=refs,
        display_name="万战寻道",
        platform="douyin",
        profile_url="https://www.douyin.com/user/x",
    )
    assert isinstance(result, WebResearchResult)
    assert result.channels_ok >= 1
    assert (refs / "01-writings.md").is_file()
    assert (refs / "06-timeline.md").is_file()
    assert "answer:" in (refs / "01-writings.md").read_text(encoding="utf-8")


def test_none_provider_writes_placeholders(tmp_path) -> None:
    refs = tmp_path / "research"
    cfg = DistillConfig(web_search_provider="none", web_research_max_parallel=1)
    result = run_six_channel_research(
        cfg=cfg,
        refs_dir=refs,
        display_name="Test Creator",
        platform="bilibili",
        provider=NoneWebSearchProvider(),
    )
    assert result.channels_ok == 0
    assert len(result.channel_status) == cfg.web_research_channels
    assert (refs / "01-writings.md").is_file()
    assert (refs / "06-timeline.md").is_file()
