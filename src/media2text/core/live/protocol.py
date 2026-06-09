from __future__ import annotations

from typing import Protocol

from media2text.core.platform.douyin.models import LiveRoomInfo


class LivePlatformAdapter(Protocol):
    def get_live_room(self, *, sec_uid: str) -> LiveRoomInfo: ...

    def resolve_stream_url(
        self,
        *,
        room_id: str,
        sec_uid: str | None = None,
        web_rid: str | None = None,
    ) -> str: ...
