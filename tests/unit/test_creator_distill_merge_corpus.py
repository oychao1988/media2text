import json

import pytest

from media2text.agent.creator_distill.collect import collect_corpus
from media2text.agent.creator_distill.merge_corpus import (
    LOCAL_BUDGET,
    META_BUDGET,
    WEB_BUDGET,
    merge_corpus_for_distill,
)

pytestmark = pytest.mark.agent


def test_merge_corpus_respects_segment_budgets(tmp_path) -> None:
    ws = tmp_path / "data"
    sec = "sec_merge"
    creator_dir = ws / "creators" / sec
    summary = creator_dir / "live" / "a.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("L" * 1000, encoding="utf-8")
    (creator_dir / "agent-manifest.json").write_text(
        json.dumps({"live": [{"summary_path": str(summary)}]}),
        encoding="utf-8",
    )
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "01-writings.md").write_text("W" * 1000, encoding="utf-8")

    corpus = collect_corpus(
        workspace=ws,
        sec_uid=sec,
        display_name="Merge Test",
        platform="douyin",
        profile_url=None,
        max_input_chars=200_000,
    )
    merged = merge_corpus_for_distill(
        local_corpus=corpus,
        refs_dir=refs,
        max_input_chars=200_000,
    )
    assert merged.meta_chars <= META_BUDGET
    assert merged.local_chars <= LOCAL_BUDGET
    assert merged.web_chars <= WEB_BUDGET
    assert "01-writings.md" in merged.text
    assert merged.total_chars == len(merged.text)


def test_merge_corpus_truncated_when_over_cap(tmp_path) -> None:
    ws = tmp_path / "data"
    sec = "sec_trunc"
    creator_dir = ws / "creators" / sec
    summary = creator_dir / "live" / "big.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("x" * 80_000, encoding="utf-8")
    (creator_dir / "agent-manifest.json").write_text(
        json.dumps({"live": [{"summary_path": str(summary)}]}),
        encoding="utf-8",
    )
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "01-writings.md").write_text("y" * 40_000, encoding="utf-8")

    corpus = collect_corpus(
        workspace=ws,
        sec_uid=sec,
        display_name="Trunc",
        platform="douyin",
        profile_url=None,
        max_input_chars=200_000,
    )
    merged = merge_corpus_for_distill(
        local_corpus=corpus,
        refs_dir=refs,
        max_input_chars=10_000,
    )
    assert merged.truncated is True
    assert merged.total_chars <= 10_000
