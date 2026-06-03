from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.summarize.base import DISCLAIMER_MD, SummaryResult
from media2text.core.summarize.sections import parse_sections_from_markdown


def _media_base(media: Path) -> Path:
    if media.name == "content.md":
        return media.with_name("content")
    if media.name.endswith(".transcript.json"):
        return media.with_name(media.name.removesuffix(".transcript.json"))
    return media


def summary_paths_for_media(media: Path) -> tuple[Path, Path]:
    if media.name == "content.md":
        return (
            media.with_name("content.summary.md"),
            media.with_name("content.summary.json"),
        )
    base = _media_base(media)
    return base.with_suffix(".summary.md"), base.with_suffix(".summary.json")


def merged_summary_paths(live_dir: Path, yyyymmdd: str) -> tuple[Path, Path]:
    stem = live_dir / f"{yyyymmdd}_merged"
    return stem.with_suffix(".summary.md"), stem.with_suffix(".summary.json")


def write_summary(
    media: Path,
    result: SummaryResult,
    *,
    source_transcript: Path,
    parse_sections: bool = True,
) -> tuple[Path, Path]:
    md_path, json_path = summary_paths_for_media(media)
    body = DISCLAIMER_MD + "\n" + result.markdown.strip() + "\n"
    md_path.write_text(body, encoding="utf-8")
    meta = {
        "engine": result.engine,
        "model": result.model,
        "provider_base_url": result.provider_base_url,
        "profile": result.profile,
        "source_transcript": str(source_transcript),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "个人研究档案整理，不构成投资咨询或买卖建议。",
        "chunks": result.chunks,
        "markdown_path": str(md_path),
    }
    if result.llm_usage:
        meta["llm_usage"] = result.llm_usage
    if parse_sections:
        sections = parse_sections_from_markdown(result.markdown)
        if sections:
            meta["sections"] = sections
    json_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path, json_path


def write_merged_summary(
    live_dir: Path,
    date_yyyymmdd: str,
    result: SummaryResult,
    *,
    sources: list[dict],
    parse_sections: bool = True,
) -> tuple[Path, Path]:
    md_path, json_path = merged_summary_paths(live_dir, date_yyyymmdd)
    body = DISCLAIMER_MD + "\n" + result.markdown.strip() + "\n"
    md_path.write_text(body, encoding="utf-8")
    meta = {
        "engine": result.engine,
        "model": result.model,
        "provider_base_url": result.provider_base_url,
        "profile": result.profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "个人研究档案整理，不构成投资咨询或买卖建议。",
        "chunks": result.chunks,
        "markdown_path": str(md_path),
        "merged": True,
        "sources": sources,
    }
    if result.llm_usage:
        meta["llm_usage"] = result.llm_usage
    if parse_sections:
        sections = parse_sections_from_markdown(result.markdown)
        if sections:
            meta["sections"] = sections
    json_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path, json_path
