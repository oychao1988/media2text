from __future__ import annotations

from dataclasses import dataclass

from media2text.core.platform.douyin.playwright_client import (
    _aweme_post_cursor_from_url,
    _aweme_post_payload_from_response,
    _aweme_post_query_matches,
    _normalize_aweme_max_cursor,
    _pick_aweme_post_payload,
    _store_aweme_post_snapshot,
)

SEC = "MS4wLjABAAAAtest"


@dataclass
class FakeResponse:
    url: str
    status: int = 200
    _body: dict | None = None

    def json(self) -> dict:
        if self._body is None:
            raise ValueError("no body")
        return self._body


def test_normalize_aweme_max_cursor() -> None:
    assert _normalize_aweme_max_cursor("") == "0"
    assert _normalize_aweme_max_cursor("99") == "99"


def test_aweme_post_query_matches() -> None:
    base = (
        "https://www.douyin.com/aweme/v1/web/aweme/post/"
        f"?sec_user_id={SEC}&max_cursor=0&count=18"
    )
    assert _aweme_post_query_matches(base, sec_uid=SEC, max_cursor="")
    assert _aweme_post_query_matches(base, sec_uid=SEC, max_cursor="0")
    assert not _aweme_post_query_matches(base, sec_uid="other", max_cursor="")
    assert not _aweme_post_query_matches(
        "https://www.douyin.com/aweme/v1/web/user/profile/other/", sec_uid=SEC, max_cursor=""
    )


def test_aweme_post_payload_from_response_ok() -> None:
    url = f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={SEC}&max_cursor=0"
    resp = FakeResponse(
        url=url,
        _body={"status_code": 0, "aweme_list": [{"aweme_id": "1"}], "has_more": 0},
    )
    payload = _aweme_post_payload_from_response(resp, sec_uid=SEC, max_cursor="")
    assert payload is not None
    assert len(payload["aweme_list"]) == 1


def test_aweme_post_payload_from_response_rejects_unsigned() -> None:
    url = f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={SEC}&max_cursor=0"
    resp = FakeResponse(url=url, _body={"status_code": 5, "aweme_list": None})
    assert _aweme_post_payload_from_response(resp, sec_uid=SEC, max_cursor="") is None


def test_pick_aweme_post_payload_prefers_larger_list() -> None:
    a = {"aweme_list": [{"aweme_id": "1"}]}
    b = {"aweme_list": [{"aweme_id": "1"}, {"aweme_id": "2"}]}
    assert _pick_aweme_post_payload([a, b]) == b


def test_store_aweme_post_snapshot_by_cursor() -> None:
    snapshots: dict[str, dict] = {}
    url0 = f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={SEC}&max_cursor=0"
    url1 = f"https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={SEC}&max_cursor=99"
    _store_aweme_post_snapshot(
        snapshots, url=url0, payload={"status_code": 0, "aweme_list": [{"aweme_id": "1"}]}
    )
    _store_aweme_post_snapshot(
        snapshots,
        url=url1,
        payload={"status_code": 0, "aweme_list": [{"aweme_id": "2"}, {"aweme_id": "3"}]},
    )
    assert _aweme_post_cursor_from_url(url0) == "0"
    assert set(snapshots.keys()) == {"0", "99"}
