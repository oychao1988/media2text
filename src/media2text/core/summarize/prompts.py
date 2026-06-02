from __future__ import annotations

from media2text.core.summarize.base import PROFILES
from media2text.core.summarize.errors import SummarizeError

_SYSTEM_LIVE = """你是直播转写内容的整理助手。根据转写片段生成结构化中文摘要。
要求：
- 仅整理转写中已表述的内容，不要新增投资建议或买卖观点
- 输出 Markdown，包含：核心观点（要点列表）、时间窗口/关键日期（引用片段时间）、板块/主题、风险提示（整理原文提及的风险）
- 不要编造未在转写中出现的事实
- 摘要需体现「不构成投资咨询或买卖建议」的合规语境"""

_SYSTEM_VOD = """你是短视频转写内容的整理助手。根据转写生成简洁中文摘要。
输出 Markdown：3-5 条要点亮点；可选「金句」（必须引用转写原文）；一行主题标签。"""

_SYSTEM_NEUTRAL = """你是动态/图文内容的整理助手。根据正文生成中性会议纪要式摘要。
输出 Markdown：主题、要点列表、待办或结论（如有）。"""

_SYSTEM_MERGE = """你是多段直播转写的合并整理助手。输入包含多个录制片段（Part N）。
要求：去重重复表述，统一结构，保留 (Part N, 时间) 引用，不新增投资建议。"""


def resolve_profile(name: str, *, media_kind: str) -> str:
    if name != "auto":
        if name not in PROFILES:
            raise SummarizeError(f"unknown profile: {name}")
        return name
    if media_kind == "live":
        return "live_market_recap"
    if media_kind == "vod":
        return "vod_highlights"
    if media_kind == "dynamic":
        return "neutral_minutes"
    raise SummarizeError(f"unknown media_kind: {media_kind}")


def _system_for_profile(profile: str, *, merge_pass: bool) -> str:
    if merge_pass:
        return _SYSTEM_MERGE
    if profile == "live_market_recap":
        return _SYSTEM_LIVE
    if profile == "vod_highlights":
        return _SYSTEM_VOD
    if profile == "neutral_minutes":
        return _SYSTEM_NEUTRAL
    raise SummarizeError(f"unknown profile: {profile}")


def build_messages(
    profile: str,
    chunk_text: str,
    *,
    merge_pass: bool = False,
) -> list[dict[str, str]]:
    system = _system_for_profile(profile, merge_pass=merge_pass)
    user = f"请整理以下转写内容：\n\n{chunk_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
