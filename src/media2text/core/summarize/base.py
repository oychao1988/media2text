from __future__ import annotations

from dataclasses import dataclass

DISCLAIMER_MD = (
    "> 个人研究档案整理，不构成投资咨询或买卖建议。请独立判断，注意风险。\n"
)

PROFILES = frozenset({
    "auto",
    "live_market_recap",
    "vod_highlights",
    "neutral_minutes",
})


@dataclass
class SummaryResult:
    engine: str
    model: str
    profile: str
    markdown: str
    chunks: int
    provider_base_url: str | None = None
    llm_usage: dict | None = None


@dataclass
class LlmUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0

    def add(self, other: LlmUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.requests += other.requests

    def copy(self) -> LlmUsage:
        return LlmUsage(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            requests=self.requests,
        )

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
        }


def usage_delta(before: LlmUsage, after: LlmUsage) -> LlmUsage:
    return LlmUsage(
        prompt_tokens=max(0, after.prompt_tokens - before.prompt_tokens),
        completion_tokens=max(0, after.completion_tokens - before.completion_tokens),
        total_tokens=max(0, after.total_tokens - before.total_tokens),
        requests=max(0, after.requests - before.requests),
    )
