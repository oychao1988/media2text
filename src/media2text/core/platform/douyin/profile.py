"""Backward-compatible re-exports; use media2text.core.platform.profile for new code."""

from media2text.core.platform.profile import (
    PROFILE_STALE_DAYS_DEFAULT,
    is_profile_stale,
    platform_session_ready,
    sync_creator_profile,
)

__all__ = [
    "PROFILE_STALE_DAYS_DEFAULT",
    "is_profile_stale",
    "platform_session_ready",
    "sync_creator_profile",
]
