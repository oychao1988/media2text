"""Six-channel public web research for Creator Distill bootstrap (nuwa Phase 1)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from media2text.agent.creator_distill.tavily_client import (
    TavilyClient,
    TavilySearchResponse,
    resolve_tavily_api_key,
)
from media2text.agent.creator_distill.web_search import (
    WebSearchProvider,
    build_web_search_provider,
)
from media2text.core.config import DistillConfig

CHANNELS: list[tuple[str, str]] = [
    ("01-writings.md", "{name} 长文 观点 体系 专栏"),
    ("02-conversations.md", "{name} 访谈 播客 直播 对话"),
    ("03-expression-dna.md", "{name} 微博 动态 语录 口头禅"),
    ("04-external-views.md", "{name} 评价 争议 分析"),
    ("05-decisions.md", "{name} 决策 立场 转折"),
    ("06-timeline.md", "{name} 经历 时间线 2024 2025 2026"),
]

_PLATFORM_HINTS = {
    "douyin": "抖音",
    "bilibili": "B站 bilibili",
}


@dataclass(frozen=True)
class WebResearchResult:
    channels_ok: int
    channel_status: dict[str, str]
    total_chars: int


def channel_has_valid_content(
    resp: TavilySearchResponse,
    *,
    denylist: list[str] | None = None,
) -> bool:
    if (resp.answer or "").strip():
        return True
    deny = denylist or []
    for r in resp.results:
        if any(d in r.url for d in deny):
            continue
        return True
    return False


def _filter_results(
    resp: TavilySearchResponse,
    *,
    denylist: list[str],
) -> list:
    out = []
    for r in resp.results:
        if any(d in r.url for d in denylist):
            continue
        out.append(r)
    return out


def _build_query(
    template: str,
    *,
    display_name: str,
    platform: str,
) -> str:
    hint = _PLATFORM_HINTS.get(platform, platform)
    return template.format(name=display_name) + f" {hint}"


def _render_channel_md(
    *,
    channel_file: str,
    query: str,
    resp: TavilySearchResponse,
    filtered_results: list,
    collected_at: str,
    error: str | None = None,
) -> str:
    title = channel_file.replace(".md", "").replace("-", " ").title()
    lines = [f"# {title}", "", f"**Query:** {query}", f"**Collected:** {collected_at} UTC", ""]
    if error:
        lines.extend(
            [
                "> 本路未找到可靠来源",
                "",
                f"**原因:** {error}",
                "",
            ]
        )
        return "\n".join(lines)

    answer = (resp.answer or "").strip()
    if answer:
        lines.extend(["## Summary", "", answer, ""])

    if filtered_results:
        lines.extend(["## Sources", ""])
        lines.append("| Title | URL | Snippet |")
        lines.append("| --- | --- | --- |")
        for r in filtered_results:
            snippet = (r.content or "").replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            lines.append(f"| {r.title} | {r.url} | {snippet} |")
        lines.append("")
    elif not answer:
        lines.extend(
            [
                "> 本路未找到可靠来源",
                "",
                "**原因:** 检索无有效结果（denylist 过滤后为空）",
                "",
            ]
        )

    return "\n".join(lines)


def _run_channel(
    *,
    channel_file: str,
    query_template: str,
    provider: WebSearchProvider,
    client: TavilyClient | None,
    cfg: DistillConfig,
    display_name: str,
    platform: str,
    refs_dir: Path,
) -> tuple[str, bool, int, str]:
    query = _build_query(query_template, display_name=display_name, platform=platform)
    collected_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    denylist = list(cfg.web_source_denylist)
    try:
        resp = provider.search(query)
        if cfg.tavily_extract_top_urls > 0 and client is not None:
            top_urls = [r.url for r in resp.results[: cfg.tavily_extract_top_urls] if r.url]
            if top_urls:
                extract_resp = client.extract(top_urls)
                by_url = {e.url: e.raw_content for e in extract_resp.results}
                enriched = []
                for r in resp.results:
                    extra = by_url.get(r.url, "")
                    content = r.content
                    if extra and extra not in content:
                        content = f"{content}\n\n{extra}".strip()
                    enriched.append(type(r)(title=r.title, url=r.url, content=content))
                resp = TavilySearchResponse(answer=resp.answer, results=enriched)

        filtered = _filter_results(resp, denylist=denylist)
        ok = channel_has_valid_content(resp, denylist=denylist)
        md = _render_channel_md(
            channel_file=channel_file,
            query=query,
            resp=resp,
            filtered_results=filtered,
            collected_at=collected_at,
        )
        status = "ok" if ok else "empty"
    except Exception as exc:
        md = _render_channel_md(
            channel_file=channel_file,
            query=query,
            resp=TavilySearchResponse("", []),
            filtered_results=[],
            collected_at=collected_at,
            error=str(exc),
        )
        ok = False
        status = "error"

    out_path = refs_dir / channel_file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return channel_file, ok, len(md), status


def run_six_channel_research(
    *,
    cfg: DistillConfig,
    refs_dir: Path,
    display_name: str,
    platform: str,
    profile_url: str | None = None,
    provider: WebSearchProvider | None = None,
) -> WebResearchResult:
    del profile_url
    refs_dir.mkdir(parents=True, exist_ok=True)
    api_key = resolve_tavily_api_key(env_key=cfg.tavily_api_key_env)
    search_provider = provider or build_web_search_provider(cfg=cfg, api_key=api_key or None)
    client: TavilyClient | None = None
    if cfg.web_search_provider != "none" and api_key:
        client = TavilyClient(api_key=api_key, timeout_sec=float(cfg.web_search_timeout_sec))

    channels = CHANNELS[: max(0, cfg.web_research_channels)]
    channel_status: dict[str, str] = {}
    channels_ok = 0
    total_chars = 0
    max_workers = max(1, cfg.web_research_max_parallel)

    def _task(item: tuple[str, str]) -> tuple[str, bool, int, str]:
        channel_file, query_template = item
        return _run_channel(
            channel_file=channel_file,
            query_template=query_template,
            provider=search_provider,
            client=client,
            cfg=cfg,
            display_name=display_name,
            platform=platform,
            refs_dir=refs_dir,
        )

    if max_workers == 1 or len(channels) <= 1:
        for item in channels:
            channel_file, ok, chars, status = _task(item)
            channel_status[channel_file] = status
            total_chars += chars
            if ok:
                channels_ok += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_task, item): item[0] for item in channels}
            for fut in as_completed(futures):
                channel_file, ok, chars, status = fut.result()
                channel_status[channel_file] = status
                total_chars += chars
                if ok:
                    channels_ok += 1

    return WebResearchResult(
        channels_ok=channels_ok,
        channel_status=channel_status,
        total_chars=total_chars,
    )
