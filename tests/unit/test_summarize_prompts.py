from media2text.core.summarize.prompts import build_messages, resolve_profile


def test_resolve_profile_auto_live() -> None:
    assert resolve_profile("auto", media_kind="live") == "live_market_recap"


def test_resolve_profile_auto_vod() -> None:
    assert resolve_profile("auto", media_kind="vod") == "vod_highlights"


def test_build_messages_live_contains_disclaimer_instruction() -> None:
    msgs = build_messages("live_market_recap", "chunk text")
    assert "不构成投资" in msgs[0]["content"] or "买卖" in msgs[0]["content"]
