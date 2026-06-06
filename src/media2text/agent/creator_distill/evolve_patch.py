"""Incremental SKILL / MEMORY patch helpers (Hermes §24.4.5)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _first_model_title(skill_md: str) -> str | None:
    match = re.search(r"^###\s+(.+)$", skill_md, re.MULTILINE)
    return match.group(1).strip() if match else None


def excerpt_from_summary(text: str, *, max_len: int = 280) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:max_len]
    return text.strip()[:max_len]


def build_heuristic_patch(
    *,
    source_id: str,
    summary_text: str,
) -> dict[str, Any]:
    """Rule-based patch when LLM is unavailable (tests / offline)."""
    excerpt = excerpt_from_summary(summary_text)
    return {
        "model_cases": [
            {
                "model_title": None,
                "case": excerpt,
                "source_id": source_id,
            }
        ],
        "stance_changes": [],
        "heuristics_add": [f"参考场次 {source_id}：{excerpt[:120]}"],
        "expression_dna_append": "",
        "memory_facts": [excerpt],
    }


def apply_skill_patch(skill_md: str, patch: dict[str, Any]) -> str:
    """Append incremental sections; never rewrite the whole file."""
    lines = skill_md.rstrip().splitlines()
    out = list(lines)

    for change in patch.get("stance_changes") or []:
        if not isinstance(change, dict):
            continue
        note = str(change.get("note") or "").strip()
        if not note:
            continue
        date = change.get("date") or datetime.now(timezone.utc).date().isoformat()
        out.extend(["", "## 立场变化", "", f"- ({date}) {note}"])

    cases = patch.get("model_cases") or []
    if cases:
        default_title = _first_model_title(skill_md) or "心智模型"
        by_title: dict[str, list[str]] = {}
        for item in cases:
            if not isinstance(item, dict):
                continue
            case = str(item.get("case") or "").strip()
            if not case:
                continue
            sid = str(item.get("source_id") or "")
            title = str(item.get("model_title") or default_title)
            bullet = f"- {case} _(source: {sid})_"
            by_title.setdefault(title, []).append(bullet)
        for title, bullets in by_title.items():
            out.extend(["", f"### {title} — 案例补充", ""])
            out.extend(bullets)

    heuristics = patch.get("heuristics_add") or []
    if heuristics:
        out.extend(["", "## 决策启发式 — 补充", ""])
        for h in heuristics:
            out.append(f"- {h}")

    dna = str(patch.get("expression_dna_append") or "").strip()
    if dna:
        out.extend(["", "## 表达 DNA — 补充", "", dna])

    return "\n".join(out).strip() + "\n"


def apply_memory_patch(
    memory_md: str,
    patch: dict[str, Any],
    *,
    source_id: str,
    max_chars: int,
) -> str:
    body = memory_md.strip()
    if body and not body.startswith("#"):
        lines = body.splitlines()
    else:
        lines = ["# MEMORY", ""]
        if body:
            lines.extend(body.splitlines()[1:] if body.startswith("#") else [body])

    facts = patch.get("memory_facts") or []
    for fact in facts:
        text = str(fact).strip()
        if not text:
            continue
        if f"source: {source_id}" in text or f"_(source: {source_id})_" in text:
            lines.append(f"- {text} _(source: {source_id})_")
        else:
            lines.append(f"- {text} _(source: {source_id})_")

    merged = "\n".join(lines).strip() + "\n"
    return trim_memory(merged, max_chars=max_chars)


def trim_memory(memory_md: str, *, max_chars: int) -> str:
    """Merge oldest bullets when MEMORY exceeds limit."""
    if len(memory_md) <= max_chars:
        return memory_md

    lines = memory_md.splitlines()
    header: list[str] = []
    bullets: list[str] = []
    for line in lines:
        if line.strip().startswith("- "):
            bullets.append(line)
        elif not bullets:
            header.append(line)
        else:
            bullets.append(line)

    while len("\n".join(header + bullets)) > max_chars and len(bullets) >= 2:
        a = bullets.pop(0)
        b = bullets.pop(0)
        merged = f"- {a.lstrip('- ').strip()} / {b.lstrip('- ').strip()}"
        bullets.insert(0, merged[: max_chars // 4])

    result = "\n".join(header + bullets).strip() + "\n"
    if len(result) > max_chars:
        result = result[: max_chars - 20].rstrip() + "\n…(truncated)\n"
    return result


def sections_patched(patch: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if patch.get("model_cases"):
        names.append("mental_models")
    if patch.get("stance_changes"):
        names.append("stance_changes")
    if patch.get("heuristics_add"):
        names.append("heuristics")
    if patch.get("expression_dna_append"):
        names.append("expression_dna")
    if patch.get("memory_facts"):
        names.append("memory")
    return names
