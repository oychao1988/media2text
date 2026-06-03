from __future__ import annotations

import json
import re
from json import JSONDecodeError
from pathlib import Path
from urllib.parse import unquote

import httpx

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.http_live import fetch_profile_api, resolve_live_via_http
from media2text.core.platform.douyin.models import AwemeItem, LiveRoomInfo, UserProfile
from media2text.core.platform.douyin.parse import (
    parse_aweme_detail_url,
    parse_aweme_post_list,
    parse_profile_html_user,
    parse_profile_live,
    parse_reflow_room,
    parse_user_profile,
)
from media2text.core.platform.douyin.playwright_client import (
    _normalize_aweme_max_cursor,
    fetch_aweme_post_snapshots_until_cursor,
    fetch_aweme_post_snapshots_via_page,
    fetch_json,
    fetch_profile_api_via_page,
    fetch_profile_html,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


class DouyinAdapterV1:
    def __init__(
        self,
        client: httpx.Client | None,
        *,
        session_path: Path | None = None,
        fixture_root: Path | None = None,
    ) -> None:
        self._client = client
        self._session_path = session_path
        self._fixture_root = fixture_root or (FIXTURE_ROOT if not client else None)
        self._aweme_post_snapshots: dict[str, dict] | None = None
        self._aweme_post_snapshots_uid: str | None = None

    def _load_fixture(self, name: str) -> dict:
        root = self._fixture_root or FIXTURE_ROOT
        return json.loads((root / name).read_text())

    def _require_session(self) -> Path:
        if self._session_path and self._session_path.is_file():
            return self._session_path
        raise AuthRequired("no session")

    def _live_room_via_playwright(self, session: Path, sec_uid: str) -> LiveRoomInfo:
        from media2text.core.platform.douyin.parse import parse_profile_html

        try:
            html = fetch_profile_html(session, sec_uid)
            return parse_profile_html(html)
        except (ParseFailed, AuthRequired):
            pass

        params = {
            "sec_user_id": sec_uid,
            "publish_video_strategy_type": "2",
            "personal_center_strategy": "1",
        }
        payload = fetch_json(
            session,
            "https://www.douyin.com/aweme/v1/web/user/profile/other/",
            params=params,
        )
        return parse_profile_live(payload)

    def get_user_profile(self, *, sec_uid: str) -> UserProfile:
        if self._fixture_root:
            return parse_user_profile(self._load_fixture("user_profile_detail.json"))

        if not self._client and not self._session_path:
            raise AuthRequired("no session")

        session = self._session_path if self._session_path and self._session_path.is_file() else None
        params = {
            "sec_user_id": sec_uid,
            "publish_video_strategy_type": "2",
            "personal_center_strategy": "1",
        }
        uri = "https://www.douyin.com/aweme/v1/web/user/profile/other/"

        try:
            if self._client:
                payload = fetch_profile_api(self._client, sec_uid)
                return parse_user_profile(payload, sec_uid=sec_uid)
        except (ParseFailed, AuthRequired, httpx.HTTPError, JSONDecodeError):
            pass

        if not session:
            raise AuthRequired("no session")

        try:
            payload = fetch_profile_api_via_page(session, sec_uid)
            return parse_user_profile(payload, sec_uid=sec_uid)
        except (ParseFailed, AuthRequired, httpx.HTTPError, JSONDecodeError):
            pass

        try:
            payload = fetch_json(session, uri, params=params)
            return parse_user_profile(payload, sec_uid=sec_uid)
        except (ParseFailed, AuthRequired, httpx.HTTPError, JSONDecodeError):
            pass

        try:
            html = fetch_profile_html(session, sec_uid)
            render = re.search(r'id="RENDER_DATA"[^>]*>([^<]+)', html)
            if render:
                data = json.loads(unquote(render.group(1)))
                profile = parse_profile_html_user(data, sec_uid=sec_uid)
                if profile and profile.display_name:
                    return profile
        except (ParseFailed, AuthRequired, json.JSONDecodeError):
            pass

        raise ParseFailed("unable to load user profile")

    def get_live_room(self, *, sec_uid: str) -> LiveRoomInfo:
        if self._fixture_root:
            data = self._load_fixture(
                "user_profile_offline.json" if sec_uid == "offline" else "user_profile_live.json"
            )
            info = parse_profile_live(data)
            if info.is_live and info.room_id:
                reflow = parse_reflow_room(self._load_fixture("reflow_live.json"))
                info.stream_flv_url = reflow.stream_flv_url
            return info

        if not self._client:
            raise AuthRequired("no session")

        session = self._session_path if self._session_path and self._session_path.is_file() else None
        try:
            info = resolve_live_via_http(self._client, sec_uid)
        except AuthRequired:
            raise
        except (ParseFailed, httpx.HTTPError, JSONDecodeError):
            if not session:
                raise
            return self._live_room_via_playwright(session, sec_uid)

        if (not info.is_live or not info.room_id) and session:
            try:
                pw_info = self._live_room_via_playwright(session, sec_uid)
                if pw_info.is_live and pw_info.room_id:
                    return pw_info
            except Exception:  # noqa: BLE001 — Playwright page/navigation flakes
                pass

        return info

    def is_live(self, *, sec_uid: str, room_id: str | None = None) -> bool:
        if room_id == "offline":
            return False
        return self.get_live_room(sec_uid=sec_uid).is_live

    def resolve_room_id(self, *, sec_uid: str) -> str | None:
        return self.get_live_room(sec_uid=sec_uid).room_id

    def resolve_stream_url(self, *, room_id: str, sec_uid: str | None = None) -> str:
        if self._fixture_root:
            reflow = parse_reflow_room(self._load_fixture("reflow_live.json"))
            if reflow.stream_flv_url:
                return reflow.stream_flv_url
            raise ParseFailed("missing stream_url in fixture")

        return self._resolve_stream_url(room_id=room_id, sec_uid=sec_uid)

    def get_room_reflow(self, *, room_id: str, sec_uid: str | None = None) -> LiveRoomInfo:
        return parse_reflow_room(
            self._fetch_reflow_payload(room_id=room_id, sec_uid=sec_uid)
        )

    @staticmethod
    def _reflow_payload_has_room(payload: dict) -> bool:
        room = payload.get("room")
        if not isinstance(room, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                room = data.get("room")
        return isinstance(room, dict) and bool(room)

    def _fetch_reflow_payload(self, *, room_id: str, sec_uid: str | None) -> dict:
        if not self._client and not self._session_path:
            raise AuthRequired("no session")

        params: dict[str, str] = {
            "room_id": room_id,
            "live_id": "1",
            "type_id": "0",
            "version_code": "99.99.99",
            "app_id": "1128",
        }
        if sec_uid:
            params["sec_user_id"] = sec_uid

        url = "https://webcast.amemv.com/webcast/room/reflow/info/"

        try:
            if self._client:
                response = self._client.get(url, params=params)
                if response.status_code < 400:
                    body = response.text.strip()
                    if body and body[0] in "{[":
                        payload = response.json()
                        if self._reflow_payload_has_room(payload):
                            return payload
        except (ParseFailed, AuthRequired, httpx.HTTPError, JSONDecodeError):
            pass

        session = self._require_session()
        try:
            return fetch_json(
                session,
                url,
                params=params,
                referer=f"https://live.douyin.com/{room_id}",
            )
        except Exception as exc:
            raise ParseFailed(f"reflow fetch failed: {exc}") from exc

    def _resolve_stream_url(self, *, room_id: str, sec_uid: str | None) -> str:
        if self._session_path and self._session_path.is_file():
            try:
                from media2text.core.platform.douyin.live_enter import (
                    resolve_stream_via_web_enter,
                )

                live_url = f"https://live.douyin.com/{room_id}"
                stream_url, _, _ = resolve_stream_via_web_enter(
                    self._session_path, live_url
                )
                return stream_url
            except ParseFailed:
                pass
            except Exception:
                pass

        reflow = self.get_room_reflow(room_id=room_id, sec_uid=sec_uid)
        if not reflow.stream_flv_url:
            raise ParseFailed("stream flv url not found")
        return reflow.stream_flv_url

    def list_awemes(
        self,
        *,
        sec_uid: str,
        max_cursor: str = "",
        count: int = 18,
    ) -> tuple[list[AwemeItem], str | None, bool]:
        if self._fixture_root:
            payload = self._load_fixture("aweme_post_page1.json")
            return parse_aweme_post_list(payload)

        if not self._client and not self._session_path:
            raise AuthRequired("no session")

        session = self._require_session()
        if self._aweme_post_snapshots_uid != sec_uid:
            self._aweme_post_snapshots = fetch_aweme_post_snapshots_via_page(session, sec_uid)
            self._aweme_post_snapshots_uid = sec_uid
        snapshots = self._aweme_post_snapshots or {}
        want = _normalize_aweme_max_cursor(max_cursor)
        payload = snapshots.get(want)
        if not payload:
            extra = fetch_aweme_post_snapshots_until_cursor(session, sec_uid, want)
            snapshots.update(extra)
            self._aweme_post_snapshots = snapshots
            payload = snapshots.get(want)
        if not payload:
            raise ParseFailed(f"aweme post page for max_cursor={want} not captured")
        return parse_aweme_post_list(payload)

    def resolve_download_url(self, *, aweme_id: str) -> str:
        if self._fixture_root:
            return parse_aweme_detail_url(self._load_fixture("aweme_detail.json"))

        if not self._client and not self._session_path:
            raise AuthRequired("no session")

        params = {"aweme_id": aweme_id}
        uri = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

        try:
            if self._client:
                response = self._client.get(uri, params=params)
                if response.status_code < 400:
                    return parse_aweme_detail_url(response.json())
        except (ParseFailed, AuthRequired, httpx.HTTPError):
            pass

        session = self._require_session()
        payload = fetch_json(session, uri, params=params)
        return parse_aweme_detail_url(payload)
