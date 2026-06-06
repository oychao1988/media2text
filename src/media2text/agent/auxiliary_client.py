"""Auxiliary LLM client for compression summaries (summarize provider or fallback)."""

from __future__ import annotations

from media2text.core.config import AppConfig


def summarize_compression(
    cfg: AppConfig,
    *,
    messages_text: str,
    reason: str = "compression",
) -> str:
    """Produce a short compression summary; falls back to deterministic truncation."""
    text = messages_text.strip()
    if not text:
        return "(empty segment compressed)"

    try:
        from media2text.core.summarize.openai_backend import (
            primary_model,
            resolve_api_key_envs,
            resolve_llm_endpoints,
        )

        endpoints = resolve_llm_endpoints(cfg.summarize.llm)
        if not endpoints:
            raise RuntimeError("no summarize endpoints")
        ep = endpoints[0]
        import os

        key_envs = resolve_api_key_envs(ep)
        api_key = ""
        for env_name in key_envs:
            api_key = os.environ.get(env_name, "")
            if api_key:
                break
        if not api_key:
            raise RuntimeError("no API key for compression")

        from openai import OpenAI  # type: ignore[reportMissingImports]

        client = OpenAI(base_url=ep.base_url, api_key=api_key)
        model = primary_model(cfg.summarize.llm)
        prompt = (
            "Summarize the following agent conversation segment for context compression. "
            "Keep key facts, decisions, and tool outcomes. Do not embed full transcripts. "
            f"Reason: {reason}.\n\n"
            f"{text[:12000]}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
        )
        choice = resp.choices[0].message.content if resp.choices else None
        if choice and choice.strip():
            return choice.strip()
    except Exception:  # noqa: BLE001
        pass

    return _fallback_summary(text)


def _fallback_summary(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = lines[:8]
    tail_note = f" … ({len(lines)} lines total)" if len(lines) > 8 else ""
    body = "\n".join(f"- {ln[:200]}" for ln in head)
    return f"[Compression summary{tail_note}]\n{body}"
