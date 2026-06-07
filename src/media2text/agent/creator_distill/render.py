"""Render distill artifacts from structured LLM JSON."""

from __future__ import annotations

import json
from typing import Any


def render_skill_md(
    *,
    slug: str,
    display_name: str,
    distill: dict[str, Any],
) -> str:
    models = distill.get("mental_models") or []
    heuristics = distill.get("decision_heuristics") or []
    voice = distill.get("expression_dna") or ""
    boundaries = distill.get("honest_boundaries") or ""
    anti_patterns = distill.get("anti_patterns") or []

    lines = [
        "---",
        f"name: {slug}",
        f"description: {display_name} 视角思维框架（蒸馏产物，非本人发言）",
        "metadata:",
        "  hermes:",
        "    protected: distill",
        "---",
        "",
        f"# {display_name} 视角",
        "",
        "## 心智模型",
        "",
    ]
    for m in models:
        if isinstance(m, dict):
            title = m.get("title") or "模型"
            body = m.get("body") or ""
            limit = m.get("limitation") or ""
            lines.append(f"### {title}")
            lines.append(body)
            if limit:
                lines.append(f"局限：{limit}")
            lines.append("")
        else:
            lines.append(f"- {m}")
    lines.extend(["", "## 决策启发式", ""])
    for h in heuristics:
        lines.append(f"- {h}")
    lines.extend(["", "## 表达 DNA", "", str(voice), "", "## 诚实边界", "", str(boundaries)])
    if anti_patterns:
        lines.extend(["", "## 反模式", ""])
        for ap in anti_patterns:
            lines.append(f"- {ap}")
    lines.append("")
    return "\n".join(lines)


def render_soul_md(*, display_name: str, distill: dict[str, Any]) -> str:
    voice = distill.get("expression_dna") or f"以研究档案口吻分析 {display_name} 的公开内容。"
    boundaries = distill.get("honest_boundaries") or (
        "本 Skill 为第三方视角蒸馏，不代表博主本人；不构成投资建议。"
    )
    return "\n".join(
        [
            f"# SOUL — {display_name}",
            "",
            "## 口吻",
            str(voice),
            "",
            "## 边界",
            str(boundaries),
            "",
        ]
    )


def render_local_corpus_md(corpus_text: str) -> str:
    return "\n".join(
        [
            "# 本地语料摘录",
            "",
            corpus_text[:50_000],
            "",
        ]
    )


def parse_distill_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("distill output must be a JSON object")
    return data
