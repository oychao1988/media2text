from __future__ import annotations


class TranscribeError(Exception):
    """Base error for transcribe configuration and runtime failures."""


class TranscribeConfigError(TranscribeError):
    """Missing API key, unsupported engine, or optional dependency not installed."""
