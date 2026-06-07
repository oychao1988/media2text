import pytest

from media2text.agent.creator_distill.gate import evaluate_bootstrap_gate

pytestmark = pytest.mark.agent


def test_proceed_when_web_ok_local_zero() -> None:
    r = evaluate_bootstrap_gate(
        web_channels_ok=2,
        local_chars=0,
        defer_until_min_chars=2000,
        bootstrap_web_research=True,
    )
    assert r.proceed is True
    assert r.deferred_reason is None


def test_defer_when_web_off_and_local_low() -> None:
    r = evaluate_bootstrap_gate(
        web_channels_ok=0,
        local_chars=100,
        defer_until_min_chars=2000,
        bootstrap_web_research=False,
    )
    assert r.proceed is False
    assert r.deferred_reason == "local_below_min"


def test_defer_when_web_on_but_all_channels_empty() -> None:
    r = evaluate_bootstrap_gate(
        web_channels_ok=0,
        local_chars=100,
        defer_until_min_chars=2000,
        bootstrap_web_research=True,
    )
    assert r.proceed is False
    assert r.deferred_reason == "web_and_local_insufficient"
