from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

import httpx

from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.bilibili.http_archive import (
    fetch_archive_page,
    resolve_video_download_url,
)
from media2text.core.platform.bilibili.http_live import (
    fetch_play_url,
    fetch_space_profile,
    resolve_live_via_http,
)
from media2text.core.platform.bilibili.parse import (
    check_api_code,
    parse_archive_cursor_list,
    parse_play_url,
    parse_room_info,
    parse_space_acc_info,
    parse_video_playurl,
)
from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


class BilibiliAdapterV1:
    def __init__(
        self,
        client: httpx.Client | None,
        *,
        session_path: Path | None = None,
        fixture_root: Path | bool | None = None,
    ) -> None:
        self._client = client
        self._session_path = session_path
        if fixture_root is False:
            self._fixture_root = None
        elif isinstance(fixture_root, Path):
            self._fixture_root = fixture_root
        elif not client:
            self._fixture_root = FIXTURE_ROOT
        else:
            self._fixture_root = None

    def _load_fixture(self, name: str) -> dict:
        root = self._fixture_root or FIXTURE_ROOT
        return json.loads((root / name).read_text())

    def get_user_profile(self, *, sec_uid: str) -> UserProfile:
        if self._fixture_root:
            return parse_space_acc_info(self._load_fixture("space_acc_info.json"))

        if not self._client:
            raise AuthRequired("no session")

        return fetch_space_profile(self._client, sec_uid)

    def get_live_room(self, *, sec_uid: str) -> LiveRoomInfo:
        if self._fixture_root:
            if sec_uid == "offline":
                return parse_room_info(self._load_fixture("room_offline.json"))
            info = parse_room_info(self._load_fixture("room_live.json"))
            if info.is_live and info.room_id:
                info.stream_flv_url = parse_play_url(self._load_fixture("play_url.json"))
            return info

        if not self._client:
            raise AuthRequired("no session")

        try:
            return resolve_live_via_http(self._client, sec_uid)
        except PlatformChanged:
            raise
        except AuthRequired:
            raise
        except (ParseFailed, httpx.HTTPError, JSONDecodeError) as exc:
            raise ParseFailed(f"live status failed: {exc}") from exc

    def is_live(self, *, sec_uid: str, room_id: str | None = None) -> bool:
        if room_id == "offline" or sec_uid == "offline":
            return False
        return self.get_live_room(sec_uid=sec_uid).is_live

    def resolve_room_id(self, *, sec_uid: str) -> str | None:
        return self.get_live_room(sec_uid=sec_uid).room_id

    def resolve_stream_url(self, *, room_id: str, sec_uid: str | None = None) -> str:
        del sec_uid
        if self._fixture_root:
            return parse_play_url(self._load_fixture("play_url.json"))

        if not self._client:
            raise AuthRequired("no session")

        return fetch_play_url(self._client, room_id)

    def list_awemes(
        self,
        *,
        sec_uid: str,
        max_cursor: str = "",
        count: int = 18,
    ) -> tuple[list[AwemeItem], str | None, bool]:
        if self._fixture_root:
            name = (
                "archive_cursor_page2.json"
                if max_cursor == "100002"
                else "archive_cursor.json"
            )
            return parse_archive_cursor_list(self._load_fixture(name))

        try:
            return fetch_archive_page(
                self._client,
                mid=sec_uid,
                max_cursor=max_cursor,
                count=count,
            )
        except PlatformChanged:
            raise
        except AuthRequired:
            raise
        except (ParseFailed, httpx.HTTPError, JSONDecodeError) as exc:
            raise ParseFailed(f"archive list failed: {exc}") from exc

    def resolve_download_url(self, *, aweme_id: str) -> str:
        if self._fixture_root:
            return parse_video_playurl(self._load_fixture("video_playurl.json"))

        if not self._client:
            raise AuthRequired("no session")

        try:
            return resolve_video_download_url(self._client, bvid=aweme_id)
        except PlatformChanged:
            raise
        except AuthRequired:
            raise
        except (ParseFailed, httpx.HTTPError, JSONDecodeError) as exc:
            raise ParseFailed(f"playurl failed for {aweme_id}: {exc}") from exc

    def check_platform_changed_fixture(self) -> None:
        """Test helper: raise PlatformChanged from fixture."""
        check_api_code(self._load_fixture("platform_changed.json"))
