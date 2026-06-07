import pytest

from media2text.agent.creator_distill.collect import collect_corpus
from media2text.agent.creator_distill.collect_local import scan_local_files
from media2text.core.config import AppConfig, LocalScanConfig

pytestmark = pytest.mark.agent


def test_scan_finds_transcript_without_manifest(tmp_path) -> None:
    ws = tmp_path / "data"
    sec = "sec_glob"
    creator_dir = ws / "creators" / sec
    tx = creator_dir / "live" / "x.transcript.md"
    tx.parent.mkdir(parents=True)
    tx.write_text("hello transcript " * 50, encoding="utf-8")

    cfg = LocalScanConfig(max_files=10)
    hits = scan_local_files(workspace=ws, sec_uid=sec, local_scan=cfg, budget=50_000)
    assert len(hits) == 1
    assert hits[0].kind == "transcript"
    assert hits[0].chars >= 100


def test_collect_corpus_merges_glob_without_manifest(tmp_path) -> None:
    ws = tmp_path / "data"
    sec = "sec_facade"
    creator_dir = ws / "creators" / sec
    summary = creator_dir / "live" / "a.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("x" * 800, encoding="utf-8")

    cfg = AppConfig.model_validate({"workspace": str(ws)})
    distill = cfg.desktop.agent.distill
    corpus = collect_corpus(
        workspace=ws,
        sec_uid=sec,
        display_name="Test",
        platform="douyin",
        profile_url=None,
        max_input_chars=distill.max_input_chars,
        local_scan=distill.local_scan,
    )
    assert corpus.total_chars >= 800
    kinds = {s.kind for s in corpus.slices}
    assert "summary" in kinds
