"""Skill slug normalization (Hermes §24.4.3)."""

from __future__ import annotations

import re


def normalize_skill_slug(display_name: str | None, *, creator_id: str) -> str:
    raw = (display_name or "creator").strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^\w\u4e00-\u9fff-]+", "", raw, flags=re.UNICODE)
    raw = raw.strip("-") or "creator"
    return f"{raw}-perspective"
