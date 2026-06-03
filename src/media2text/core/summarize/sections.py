from __future__ import annotations

import re


def parse_sections_from_markdown(markdown: str) -> list[dict[str, str]]:
    """Split LLM markdown on ## headings into structured sections for .summary.json."""
    text = markdown.strip()
    if not text or not re.search(r"(?m)^##\s+", text):
        return []

    parts = re.split(r"(?m)^##\s+", text)
    sections: list[dict[str, str]] = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not title:
            continue
        sections.append({"title": title, "content": body})
    return sections
