"""Verify Douyin live probe paths: signed HTTP enter vs reflow vs Playwright profile.

Usage (from repo root, with venv):
  python scripts/verify_douyin_live_http.py
  python scripts/verify_douyin_live_http.py --sec-uid MS4wLjAB... --web-rid 7649404054766291754
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.platform.douyin.live_enter import (
    flv_from_room_dict,
    resolve_web_rid_from_profile_page,
    room_from_enter_payload,
)
from media2text.core.platform.douyin.parse import parse_profile_live, parse_reflow_room
from media2text.core.platform.douyin.signing.abogus import ABogus, BrowserFingerprintGenerator
from media2text.core.platform.douyin.http_live import fetch_profile_api

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

DEFAULT_SEC_UIDS = [
    "MS4wLjABAAAA7YPC9dXg8FUn8pQyjPmNOQ5FQ8bzW0Zx4TRDLOEexISBMINkAAfLTsnTDp9l3oQb",  # 产品老曾
    "MS4wLjABAAAAAPIhDCpw5HrIqj9vatt5rkaXz3Pk4Bzvz62IxLxkwWC70TF1VeKVPQw10WVH_-d5",  # 万战寻道
]


def _false_ms_token(length: int = 120) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length)) + "=="


def _sign_query(base_url: str, query: str, *, user_agent: str = UA) -> tuple[str, str]:
    fp = BrowserFingerprintGenerator.generate_fingerprint("Chrome")
    signer = ABogus(fp=fp, user_agent=user_agent)
    signed_query, _ab, ua, _ = signer.generate_abogus(query, "")
    return f"{base_url}?{signed_query}", ua


def refresh_ttwid_cookie(client: httpx.Client) -> str | None:
    """LyzenX-style ttwid refresh via live.douyin.com (no browser)."""
    nonce = f"0{random.randint(10**15, 10**16 - 1)}"
    headers = {
        "User-Agent": UA,
        "cookie": f"__ac_nonce={nonce}",
    }
    resp = client.get("https://live.douyin.com/", headers=headers)
    ttwid = resp.cookies.get("ttwid")
    if ttwid:
        client.cookies.set("ttwid", ttwid, domain=".douyin.com")
    return ttwid


def probe_http_profile(client: httpx.Client, sec_uid: str) -> dict:
    t0 = time.perf_counter()
    out: dict = {"path": "http_profile/other", "sec_uid": sec_uid}
    try:
        payload = fetch_profile_api(client, sec_uid)
        info = parse_profile_live(payload)
        out.update(
            {
                "ok": True,
                "is_live": info.is_live,
                "room_id": info.room_id,
                "web_rid": info.web_rid,
                "has_flv": bool(info.stream_flv_url),
                "title": info.title,
                "ms": round((time.perf_counter() - t0) * 1000),
            }
        )
    except Exception as exc:
        out.update({"ok": False, "error": str(exc), "ms": round((time.perf_counter() - t0) * 1000)})
    return out


def probe_http_reflow(client: httpx.Client, room_id: str, sec_uid: str) -> dict:
    t0 = time.perf_counter()
    out: dict = {
        "path": "http_reflow/info",
        "room_id": room_id,
        "sec_uid": sec_uid,
    }
    params = {
        "room_id": room_id,
        "live_id": "1",
        "type_id": "0",
        "version_code": "99.99.99",
        "app_id": "1128",
        "sec_user_id": sec_uid,
    }
    url = "https://webcast.amemv.com/webcast/room/reflow/info/"
    try:
        resp = client.get(url, params=params, headers={"Referer": f"https://live.douyin.com/{room_id}"})
        body = resp.text.strip()
        out["http_status"] = resp.status_code
        out["body_len"] = len(body)
        if resp.status_code >= 400 or not body:
            out.update({"ok": False, "error": "empty or error response", "ms": round((time.perf_counter() - t0) * 1000)})
            return out
        payload = resp.json()
        info = parse_reflow_room(payload)
        out.update(
            {
                "ok": True,
                "is_live": info.is_live,
                "room_id": info.room_id,
                "has_flv": bool(info.stream_flv_url),
                "title": info.title,
                "ms": round((time.perf_counter() - t0) * 1000),
            }
        )
    except Exception as exc:
        out.update({"ok": False, "error": str(exc), "ms": round((time.perf_counter() - t0) * 1000)})
    return out


def resolve_web_rid_from_live_page(client: httpx.Client, profile_room_id: str) -> str | None:
    """Profile room_id is internal id; enter API needs web_rid from live page HTML."""
    import re

    resp = client.get(f"https://live.douyin.com/{profile_room_id}")
    if resp.status_code >= 400:
        return None
    match = re.search(r"web_rid[\"']?\s*[:=]\s*[\"']?(\d+)", resp.text)
    return match.group(1) if match else None


def probe_http_enter(client: httpx.Client, web_rid: str, sec_uid: str | None = None) -> dict:
    t0 = time.perf_counter()
    out: dict = {"path": "http_signed_enter", "web_rid": web_rid, "sec_uid": sec_uid}
    ms_token = client.cookies.get("msToken") or _false_ms_token()
    params = {
        "aid": "6383",
        "app_name": "douyin_web",
        "live_id": "1",
        "device_platform": "web",
        "language": "zh-CN",
        "enter_from": "web_live",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "139.0.0.0",
        "web_rid": web_rid,
        "enter_source": "",
        "is_need_double_stream": "false",
        "msToken": ms_token,
    }
    if sec_uid:
        params["sec_user_id"] = sec_uid
    base = "https://live.douyin.com/webcast/room/web/enter/"
    query = urlencode(params)
    try:
        signed_url, ua = _sign_query(base, query)
        resp = client.get(
            signed_url,
            headers={
                "User-Agent": ua,
                "Referer": f"https://live.douyin.com/{web_rid}",
            },
        )
        body = resp.content
        out["http_status"] = resp.status_code
        out["body_len"] = len(body)
        preview = body[:200].decode("utf-8", errors="replace") if body else ""
        if "系统繁忙" in preview or "risk" in preview.lower():
            out["risk_hint"] = True
        if resp.status_code >= 400 or not body:
            out.update(
                {
                    "ok": False,
                    "error": preview or "empty body",
                    "ms": round((time.perf_counter() - t0) * 1000),
                }
            )
            return out
        payload = resp.json()
        room = room_from_enter_payload(payload)
        if not room:
            out.update(
                {
                    "ok": False,
                    "error": "no room in enter payload (likely offline)",
                    "status_code_field": payload.get("status_code"),
                    "ms": round((time.perf_counter() - t0) * 1000),
                }
            )
            return out
        status = room.get("status")
        flv = flv_from_room_dict(room)
        out.update(
            {
                "ok": True,
                "room_status": status,
                "is_live": status == 2,
                "internal_room_id": str(room.get("id_str") or room.get("id") or ""),
                "has_flv": bool(flv),
                "title": room.get("title"),
                "ms": round((time.perf_counter() - t0) * 1000),
            }
        )
    except Exception as exc:
        out.update({"ok": False, "error": str(exc), "ms": round((time.perf_counter() - t0) * 1000)})
    return out


def probe_playwright_profile(session: Path, sec_uid: str) -> dict:
    from media2text.core.platform.douyin.adapter import DouyinAdapterV1

    t0 = time.perf_counter()
    out: dict = {"path": "playwright_profile", "sec_uid": sec_uid}
    try:
        adapter = DouyinAdapterV1(None, session_path=session)
        info = adapter.get_live_room(sec_uid=sec_uid)
        out.update(
            {
                "ok": True,
                "is_live": info.is_live,
                "room_id": info.room_id,
                "title": info.title,
                "ms": round((time.perf_counter() - t0) * 1000),
            }
        )
    except Exception as exc:
        out.update({"ok": False, "error": str(exc), "ms": round((time.perf_counter() - t0) * 1000)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-uid", action="append", dest="sec_uids")
    parser.add_argument("--web-rid", help="Known web_rid for enter/reflow (optional)")
    parser.add_argument("--skip-playwright", action="store_true")
    parser.add_argument("--session", type=Path, default=ROOT / "data/sessions/douyin.json")
    args = parser.parse_args()

    session = args.session
    if not session.is_file():
        print(json.dumps({"error": f"no session at {session}"}, ensure_ascii=False))
        return 2

    sec_uids = args.sec_uids or DEFAULT_SEC_UIDS
    client = client_from_storage(session)
    ttwid = refresh_ttwid_cookie(client)
    results: list[dict] = [{"step": "ttwid_refresh", "ttwid": bool(ttwid)}]

    for sec_uid in sec_uids:
        block: dict = {"sec_uid": sec_uid, "probes": []}
        block["probes"].append(probe_http_profile(client, sec_uid))

        profile_probe = block["probes"][0]
        profile_room_id = profile_probe.get("room_id") if profile_probe.get("ok") else None
        web_rid = args.web_rid
        if profile_probe.get("ok") and profile_probe.get("web_rid"):
            web_rid = web_rid or profile_probe.get("web_rid")
        if profile_room_id and not web_rid:
            web_rid = resolve_web_rid_from_profile_page(client, sec_uid)
            block["web_rid_from_profile_html"] = web_rid
        if profile_room_id and not web_rid:
            web_rid = resolve_web_rid_from_live_page(client, profile_room_id)
            block["web_rid_resolved"] = web_rid
            block["profile_room_id"] = profile_room_id

        if profile_room_id:
            block["probes"].append(probe_http_reflow(client, profile_room_id, sec_uid))
        if web_rid:
            block["probes"].append(probe_http_enter(client, web_rid, sec_uid))
        elif profile_room_id:
            block["probes"].append(
                {
                    "path": "http_signed_enter",
                    "skipped": "could not resolve web_rid from live page",
                    "profile_room_id": profile_room_id,
                }
            )
        else:
            block["probes"].append({"path": "http_reflow/enter", "skipped": "offline or no room_id"})

        if not args.skip_playwright:
            block["probes"].append(probe_playwright_profile(session, sec_uid))

        results.append(block)

    # Historical room_id smoke (offline enter should still parse)
    if args.web_rid:
        results.append(
            {
                "sec_uid": None,
                "note": "web_rid_only",
                "probes": [
                    probe_http_enter(client, args.web_rid, None),
                    probe_http_reflow(client, args.web_rid, sec_uids[0]),
                ],
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
