"""Corpus collection for creator distill bootstrap (Phase Collect)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusSlice:
    path: str
    kind: str
    chars: int
    text: str


@dataclass(frozen=True)
class CollectedCorpus:
    total_chars: int
    slices: list[CorpusSlice]
    manifest_path: str | None


def _resolve_path(workspace: Path, sec_uid: str, ref: str) -> Path:
    p = Path(ref)
    if p.is_absolute():
        return p
    return workspace / "creators" / sec_uid / ref


def _read_text(path: Path, *, budget: int) -> str | None:
    if budget <= 0 or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) > budget:
        text = text[:budget]
    return text


def _paths_for_item(workspace: Path, sec_uid: str, item: dict) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for key, kind in (
        ("summary_path", "summary"),
        ("transcript_path", "transcript"),
        ("content_md", "dynamic"),
    ):
        ref = item.get(key)
        if ref:
            out.append((kind, _resolve_path(workspace, sec_uid, str(ref))))
    return out


def collect_corpus(
    *,
    workspace: Path,
    sec_uid: str,
    display_name: str | None,
    platform: str,
    profile_url: str | None,
    max_input_chars: int,
    max_items: int = 20,
) -> CollectedCorpus:
    """Merge manifest metadata + local summary/transcript/content bodies."""
    creator_dir = workspace / "creators" / sec_uid
    manifest_path = creator_dir / "agent-manifest.json"
    slices: list[CorpusSlice] = []
    budget = max_input_chars

    header_lines = [
        f"# Creator: {display_name or sec_uid}",
        f"Platform: {platform}",
    ]
    if profile_url:
        header_lines.append(f"Profile: {profile_url}")
    header = "\n".join(header_lines) + "\n\n"
    if budget > 0:
        take = min(len(header), budget)
        slices.append(CorpusSlice(path="meta", kind="meta", chars=take, text=header[:take]))
        budget -= take

    items: list[dict] = []
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            items = list(data.get("live") or data.get("items") or [])[:max_items]
        except (OSError, json.JSONDecodeError):
            items = []

    seen: set[str] = set()
    for item in items:
        if budget <= 0:
            break
        for kind, path in _paths_for_item(workspace, sec_uid, item):
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            text = _read_text(path, budget=budget)
            if not text:
                continue
            rel = (
                str(path.relative_to(workspace))
                if path.is_relative_to(workspace)
                else str(path)
            )
            slices.append(CorpusSlice(path=rel, kind=kind, chars=len(text), text=text))
            budget -= len(text)

    total = sum(s.chars for s in slices)
    return CollectedCorpus(
        total_chars=total,
        slices=slices,
        manifest_path=str(manifest_path) if manifest_path.is_file() else None,
    )


def corpus_plain_text(corpus: CollectedCorpus) -> str:
    parts = [s.text for s in corpus.slices if s.text]
    return "\n\n---\n\n".join(parts)
