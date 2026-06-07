"""Merge local manifest/glob corpus with web research refs for distill LLM."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from media2text.agent.creator_distill.collect import CollectedCorpus
from media2text.agent.creator_distill.web_research import CHANNELS

META_BUDGET = 2_000
LOCAL_BUDGET = 60_000
WEB_BUDGET = 50_000


@dataclass(frozen=True)
class MergedCorpus:
    text: str
    truncated: bool
    meta_chars: int
    local_chars: int
    web_chars: int
    total_chars: int


def local_chars_from_corpus(corpus: CollectedCorpus) -> int:
    return sum(s.chars for s in corpus.slices if s.kind != "meta" and s.path != "meta")


def _take(text: str, budget: int) -> tuple[str, bool]:
    if budget <= 0:
        return "", bool(text)
    if len(text) <= budget:
        return text, False
    return text[:budget], True


def merge_corpus_for_distill(
    *,
    local_corpus: CollectedCorpus,
    refs_dir: Path | None,
    max_input_chars: int,
    meta_budget: int = META_BUDGET,
    local_budget: int = LOCAL_BUDGET,
    web_budget: int = WEB_BUDGET,
) -> MergedCorpus:
    remaining = max(0, max_input_chars)
    truncated = False
    parts: list[str] = []

    meta_slices = [s for s in local_corpus.slices if s.kind == "meta" or s.path == "meta"]
    local_slices = [s for s in local_corpus.slices if s not in meta_slices]

    meta_budget_eff = min(meta_budget, remaining)
    meta_text = "\n\n".join(s.text for s in meta_slices if s.text)
    meta_part, t = _take(meta_text, meta_budget_eff)
    truncated = truncated or t
    meta_chars = len(meta_part)
    remaining -= meta_chars
    if meta_part:
        parts.append(f"## Meta\n\n{meta_part}")

    local_budget_eff = min(local_budget, remaining)
    local_text = "\n\n---\n\n".join(s.text for s in local_slices if s.text)
    local_part, t = _take(local_text, local_budget_eff)
    truncated = truncated or t
    local_chars = len(local_part)
    remaining -= local_chars
    if local_part:
        parts.append(f"## Local corpus\n\n{local_part}")

    web_budget_eff = min(web_budget, remaining)
    web_chunks: list[str] = []
    if refs_dir is not None and refs_dir.is_dir():
        for channel_file, _ in CHANNELS:
            path = refs_dir / channel_file
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            web_chunks.append(f"### {channel_file}\n\n{content}")
    web_text = "\n\n".join(web_chunks)
    web_part, t = _take(web_text, web_budget_eff)
    truncated = truncated or t
    web_chars = len(web_part)
    if web_part:
        parts.append(f"## Web research\n\n{web_part}")

    text = "\n\n---\n\n".join(parts)
    if len(text) > max_input_chars:
        text = text[:max_input_chars]
        truncated = True
    return MergedCorpus(
        text=text,
        truncated=truncated,
        meta_chars=meta_chars,
        local_chars=local_chars,
        web_chars=web_chars,
        total_chars=len(text),
    )
