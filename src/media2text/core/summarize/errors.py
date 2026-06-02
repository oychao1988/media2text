from __future__ import annotations


class SummarizeError(Exception):
    """Base error for summarize configuration and runtime failures."""


class SummarizeConfigError(SummarizeError):
    """Missing API key, unsupported engine, or optional dependency not installed."""
