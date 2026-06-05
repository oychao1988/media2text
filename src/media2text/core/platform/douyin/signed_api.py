"""Signed Douyin web API requests (a_bogus / X-Bogus) for aweme/detail."""

from __future__ import annotations

import json
import random
import string
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from media2text.core.platform.douyin.signing.abogus import ABogus, BrowserFingerprintGenerator
from media2text.core.platform.douyin.signing.xbogus import XBogus

_BASE = "https://www.douyin.com"
_DETAIL_AIDS = ("6383", "1128")
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def _load_cookies(session_file: Path) -> dict[str, str]:
    data = json.loads(session_file.read_text())
    return {c["name"]: c["value"] for c in data.get("cookies", [])}


def _false_ms_token() -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(182)) + "=="


def _default_query(cookies: dict[str, str]) -> dict[str, Any]:
    ms_token = (cookies.get("msToken") or "").strip() or _false_ms_token()
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "pc_libra_divert": "Windows",
        "version_code": "290100",
        "version_name": "29.1.0",
        "cookie_enabled": "true",
        "screen_width": "1536",
        "screen_height": "864",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "139.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "139.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "16",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "200",
        "support_h265": "1",
        "support_dash": "1",
        "uifid": "",
        "msToken": ms_token,
    }


def _sign_url(url: str, *, user_agent: str) -> tuple[str, str]:
    try:
        browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Chrome")
        signer = ABogus(fp=browser_fp, user_agent=user_agent)
        params_with_ab, _ab, ua, _body = signer.generate_abogus(url.split("?", 1)[1], "")
        return f"{url.split('?', 1)[0]}?{params_with_ab}", ua
    except Exception:
        signed, ua, _xb = XBogus(user_agent=user_agent).build(url)
        return signed, ua


def _request_json(
    client: httpx.Client,
    path: str,
    params: dict[str, Any],
    *,
    user_agent: str = _UA,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    delays = [1, 2, 5]
    query = urlencode(params)
    base_url = f"{_BASE}{path}"

    for attempt in range(max_retries):
        signed_url, ua = _sign_url(f"{base_url}?{query}", user_agent=user_agent)
        response = client.get(signed_url, headers={"User-Agent": ua})
        if response.status_code != 200:
            if attempt + 1 < max_retries:
                time.sleep(delays[min(attempt, len(delays) - 1)])
            continue
        body = response.content
        if not body:
            if attempt + 1 < max_retries:
                time.sleep(delays[min(attempt, len(delays) - 1)])
            continue
        try:
            return response.json()
        except json.JSONDecodeError:
            if attempt + 1 < max_retries:
                time.sleep(delays[min(attempt, len(delays) - 1)])
    return None


def fetch_aweme_detail(session_file: Path, aweme_id: str) -> dict[str, Any] | None:
    """Fetch aweme_detail via signed aweme/detail (tries aid 6383 then 1128)."""
    cookies = _load_cookies(session_file)
    headers = {
        "User-Agent": _UA,
        "Referer": "https://www.douyin.com/?recommend=1",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    with httpx.Client(cookies=cookies, headers=headers, timeout=30.0, follow_redirects=True) as client:
        for aid in _DETAIL_AIDS:
            params = _default_query(cookies)
            params.update({"aweme_id": aweme_id, "aid": aid})
            data = _request_json(client, "/aweme/v1/web/aweme/detail/", params)
            if not data:
                continue
            detail = data.get("aweme_detail")
            if isinstance(detail, dict):
                return detail
            filter_info = data.get("filter_detail")
            if isinstance(filter_info, dict) and filter_info.get("filter_reason"):
                continue
            break
    return None
