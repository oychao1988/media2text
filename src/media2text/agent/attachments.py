"""Context attachment helpers for agent binding + prompts."""

from __future__ import annotations

from typing import Any


def _doc_type(item: dict[str, Any]) -> str:
    return str(item.get("doc_type") or item.get("docType") or "")


def dedupe_by_path(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in attachments:
        path = str(item.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(item)
    return out


def filter_by_context_mode(
    attachments: list[dict[str, Any]],
    context_mode: str,
) -> list[dict[str, Any]]:
    if context_mode == "both":
        return attachments
    return [a for a in attachments if _doc_type(a) == context_mode]


def legacy_binding_to_attachments(binding: dict[str, Any]) -> list[dict[str, Any]]:
    raw = binding.get("attachments")
    if isinstance(raw, list) and raw:
        return dedupe_by_path([a for a in raw if isinstance(a, dict)])
    out: list[dict[str, Any]] = []
    creator_id = binding.get("creator_id") or "unknown"
    session_kind = binding.get("session_kind") or "live"
    item_id = binding.get("session_id") or "legacy"
    transcript_path = binding.get("transcript_path")
    summary_path = binding.get("summary_path")
    if transcript_path:
        out.append(
            {
                "id": f"transcript:{transcript_path}",
                "docType": "transcript",
                "path": transcript_path,
                "label": str(transcript_path).split("/")[-1],
                "creatorId": creator_id,
                "creatorName": str(creator_id),
                "sessionKind": session_kind,
                "itemId": item_id,
                "source": "session",
            }
        )
    if summary_path:
        out.append(
            {
                "id": f"summary:{summary_path}",
                "docType": "summary",
                "path": summary_path,
                "label": str(summary_path).split("/")[-1],
                "creatorId": creator_id,
                "creatorName": str(creator_id),
                "sessionKind": session_kind,
                "itemId": item_id,
                "source": "session",
            }
        )
    return out


def format_attachments_block(
    attachments: list[dict[str, Any]],
    *,
    context_mode: str,
) -> str:
    filtered = filter_by_context_mode(attachments, context_mode)
    if not filtered:
        return ""
    lines = ["附加文档:"]
    for item in filtered:
        doc = _doc_type(item)
        doc_label = "转写" if doc == "transcript" else "摘要" if doc == "summary" else doc
        label = item.get("label") or item.get("path")
        creator = item.get("creatorName") or item.get("creator_name") or ""
        path = item.get("path") or ""
        prefix = f"{creator} · " if creator else ""
        lines.append(f"- [{doc_label}] {prefix}{label} ({path})")
    return "\n".join(lines)
