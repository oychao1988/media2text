"""Map agent runtime failures to user-facing chat text."""

from __future__ import annotations


def user_facing_agent_error(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc).strip()
    if name == "AuthenticationError" or "401" in text or "Unauthorized" in text:
        return "LLM API 认证失败，请在「系统配置 · AI」中检查对应 Provider 的 API Key。"
    if name == "RateLimitError" or "429" in text:
        return "LLM API 请求过于频繁，请稍后再试。"
    if name == "APIConnectionError" or "Connection" in name:
        return "无法连接 LLM API，请检查网络与 Provider Base URL。"
    if text:
        if len(text) > 240:
            text = text[:240] + "…"
        return f"Agent 执行失败：{text}"
    return "Agent 执行失败，请稍后重试。"
