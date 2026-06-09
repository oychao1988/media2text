from __future__ import annotations

from typing import Protocol

from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile


class PlatformAdapter(Protocol):
    """Platform-specific HTTP/Playwright facade (Douyin MVP; Bilibili in P6)."""

    def get_user_profile(self, *, sec_uid: str) -> UserProfile: ...

    def get_live_room(self, *, sec_uid: str) -> LiveRoomInfo: ...

    def is_live(self, *, sec_uid: str, room_id: str | None = None) -> bool: ...

    def resolve_room_id(self, *, sec_uid: str) -> str | None: ...

    def resolve_stream_url(
        self,
        *,
        room_id: str,
        sec_uid: str | None = None,
        web_rid: str | None = None,
    ) -> str: ...

    def list_awemes(
        self,
        *,
        sec_uid: str,
        max_cursor: str = "",
        count: int = 18,
    ) -> tuple[list[AwemeItem], str | None, bool]: ...

    def resolve_download_url(self, *, aweme_id: str) -> str: ...
