#!/usr/bin/env python3
"""Douyin live FLV → ffmpeg PCM → Deepgram streaming STT (experimental).

Resolves pull URL via DouyinAdapter (needs data/sessions/douyin.json), pipes mono
16 kHz PCM into Deepgram listen.v1 WebSocket (nova-3). Not part of the CLI.

Example:
  source .venv/bin/activate
  export DEEPGRAM_API_KEY=...
  python scripts/test_douyin_live_deepgram_stream.py \\
    'https://www.douyin.com/follow/live/628224832373?anchor_id=3417712764128247' \\
    -t 60
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from deepgram import DeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

from playwright.sync_api import sync_playwright

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage


def parse_live_ref(url_or_room: str) -> tuple[str, str | None]:
    """Return (room_id, sec_uid_or_none)."""
    raw = url_or_room.strip()
    if raw.isdigit():
        return raw, None

    parsed = urlparse(raw)
    path = parsed.path or ""

    m = re.search(r"live\.douyin\.com/(\d+)", raw, re.I)
    if m:
        room_id = m.group(1)
    else:
        m = re.search(r"/follow/live/(\d+)", path)
        if not m:
            m = re.search(r"/live/(\d+)", path)
        if not m:
            raise ValueError(f"cannot parse room_id from: {url_or_room}")
        room_id = m.group(1)

    sec_uid = None
    qs = parse_qs(parsed.query)
    for key in ("sec_user_id", "sec_uid"):
        if qs.get(key):
            sec_uid = qs[key][0]
            break
    return room_id, sec_uid


def build_adapter(cfg: AppConfig) -> DouyinAdapterV1:
    ws = cfg.ensure_workspace()
    session = session_path(ws)
    if not session.is_file():
        raise AuthRequired(
            f"Douyin session missing at {session}; run: media2text auth login --platform douyin"
        )
    client = client_from_storage(session)
    return DouyinAdapterV1(client, session_path=session)


def _flv_from_room_dict(room: dict) -> str | None:
    stream_url = room.get("stream_url") or {}
    flv_pull = stream_url.get("flv_pull_url")
    if isinstance(flv_pull, dict) and flv_pull:
        for key in ("HD1", "SD1", "FULL_HD1"):
            url = flv_pull.get(key)
            if isinstance(url, str) and url:
                return url
        return next((v for v in flv_pull.values() if isinstance(v, str) and v), None)
    if isinstance(flv_pull, str) and flv_pull:
        return flv_pull
    return None


def _room_from_enter_payload(payload: dict) -> dict | None:
    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
        room = data.get("room")
        if isinstance(room, dict):
            return room
    room = payload.get("room")
    return room if isinstance(room, dict) else None


def resolve_stream_via_live_page(session: Path, live_url: str) -> tuple[str, str, str | None]:
    """Open Douyin live page and capture webcast/room/web/enter pull URL."""
    enter_payload: dict | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(session))
        page = context.new_page()

        def on_response(response) -> None:
            nonlocal enter_payload
            if "webcast/room/web/enter" not in response.url or response.status != 200:
                return
            try:
                enter_payload = response.json()
            except Exception:
                return

        page.on("response", on_response)
        page.goto(live_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8_000)
        final_url = page.url
        browser.close()

    if not enter_payload:
        raise ParseFailed(
            f"no webcast/room/web/enter response for {live_url} (final={final_url})"
        )

    room = _room_from_enter_payload(enter_payload)
    if not room:
        raise ParseFailed("enter response has no room payload (offline or parse drift)")

    room_id = str(room.get("id_str") or room.get("id") or "")
    title = room.get("title")
    status = room.get("status")
    stream_flv_url = _flv_from_room_dict(room)
    if not stream_flv_url:
        raise ParseFailed(f"enter room {room_id or '?'} has no flv_pull_url (status={status})")
    if status not in (2, "2", None):
        print(f"[warn] room status={status} (expected 2=live); trying pull URL anyway")
    label = f"{title} (id={room_id})" if title else f"id={room_id}"
    print(f"[room] {label}")
    return stream_flv_url, room_id, title if isinstance(title, str) else None


def resolve_stream_url(
    adapter: DouyinAdapterV1,
    *,
    room_id: str,
    sec_uid: str | None,
    live_page_url: str | None = None,
    session: Path | None = None,
) -> tuple[str, str | None]:
    if live_page_url and session:
        stream_url, resolved_id, title = resolve_stream_via_live_page(session, live_page_url)
        print(f"[resolve] web enter ok (page_room={room_id}, room_id={resolved_id})")
        return stream_url, title

    reflow = adapter.get_room_reflow(room_id=room_id, sec_uid=sec_uid)
    if not reflow.is_live:
        print(f"[warn] reflow reports offline (room_id={room_id}); trying stream URL anyway")
    if not reflow.stream_flv_url:
        raise ParseFailed(f"no flv pull url for room {room_id}")
    title = reflow.title or ""
    if title:
        print(f"[room] {title} (id={room_id})")
    else:
        print(f"[room] id={room_id}")
    return reflow.stream_flv_url, title


def ffmpeg_live_pcm_pipe(
    stream_url: str,
    *,
    duration_sec: float | None,
    ffmpeg: str = "ffmpeg",
) -> subprocess.Popen[bytes]:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
        "-i",
        stream_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(duration_sec)])
    cmd.append("-")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_streaming_stt(
    *,
    stream_url: str,
    api_key: str,
    model: str,
    language: str,
    duration_sec: float,
    smart_format: bool,
    ffmpeg: str,
) -> int:
    client = DeepgramClient(api_key=api_key)
    proc = ffmpeg_live_pcm_pipe(stream_url, duration_sec=duration_sec, ffmpeg=ffmpeg)
    stop_at = time.monotonic() + duration_sec + 15

    with client.listen.v1.connect(
        model=model,
        language=language,
        smart_format=smart_format,
        punctuate=True,
        encoding="linear16",
        sample_rate="16000",
        channels="1",
    ) as connection:
        ready = threading.Event()

        def on_message(result) -> None:
            if not isinstance(result, ListenV1Results):
                return
            channel = result.channel
            if not channel.alternatives:
                return
            alt = channel.alternatives[0]
            transcript = (alt.transcript or "").strip()
            if not transcript:
                return
            is_final = result.is_final if result.is_final is not None else True
            tag = "final" if is_final else "interim"
            print(f"[{tag}] {transcript}", flush=True)

        connection.on(EventType.OPEN, lambda _: ready.set())
        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.ERROR, lambda err: print(f"[deepgram error] {err}", file=sys.stderr))

        def feed_pcm() -> None:
            ready.wait()
            assert proc.stdout is not None
            chunk_size = 3200  # ~100ms @ 16kHz mono s16le
            try:
                while time.monotonic() < stop_at:
                    chunk = proc.stdout.read(chunk_size)
                    if not chunk:
                        break
                    connection.send_media(chunk)
            finally:
                connection.send_close_stream()

        feeder = threading.Thread(target=feed_pcm, daemon=True)
        feeder.start()
        print(
            f"[start] streaming STT for {duration_sec:.0f}s "
            f"(model={model}, language={language})",
            flush=True,
        )
        connection.start_listening()

    proc.wait(timeout=10)
    if proc.stderr:
        err = proc.stderr.read().decode("utf-8", errors="replace").strip()
        if err:
            print(f"[ffmpeg stderr] {err}", file=sys.stderr)
    return proc.returncode or 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "live",
        help="Douyin live URL, live.douyin.com/<room_id>, or numeric room_id",
    )
    parser.add_argument(
        "--stream-url",
        help="Skip resolve; use this FLV/HLS pull URL directly",
    )
    parser.add_argument(
        "--use-page-enter",
        action="store_true",
        help="Resolve pull URL via live page webcast/room/web/enter (for numeric room_id)",
    )
    parser.add_argument("--sec-uid", help="Optional sec_user_id for reflow API")
    parser.add_argument("--api-key", default=os.environ.get("DEEPGRAM_API_KEY", ""))
    parser.add_argument("--model", default="nova-3")
    parser.add_argument("--language", default="zh")
    parser.add_argument("-t", "--duration", type=float, default=60.0)
    parser.add_argument("--no-smart-format", action="store_true")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    if not args.api_key.strip():
        sys.exit("Set DEEPGRAM_API_KEY or pass --api-key")

    cfg = AppConfig.load()

    if args.stream_url:
        stream_url = args.stream_url
        print(f"[resolve] using provided stream URL ({len(stream_url)} chars)")
    else:
        live_input = args.live.strip()
        is_page_url = live_input.startswith("http://") or live_input.startswith("https://")
        try:
            room_id, sec_uid = parse_live_ref(live_input)
        except ValueError as exc:
            sys.exit(str(exc))
        sec_uid = args.sec_uid or sec_uid
        print(f"[resolve] page_room={room_id}" + (f" sec_uid={sec_uid[:20]}..." if sec_uid else ""))
        try:
            adapter = build_adapter(cfg)
            session = session_path(cfg.ensure_workspace())
            live_page_url = live_input if is_page_url else f"https://live.douyin.com/{room_id}"
            if is_page_url or args.use_page_enter:
                stream_url, _ = resolve_stream_url(
                    adapter,
                    room_id=room_id,
                    sec_uid=sec_uid,
                    live_page_url=live_page_url,
                    session=session,
                )
            else:
                stream_url, _ = resolve_stream_url(
                    adapter,
                    room_id=room_id,
                    sec_uid=sec_uid,
                )
        except AuthRequired as exc:
            sys.exit(str(exc))
        except ParseFailed as exc:
            sys.exit(
                f"{exc}\n"
                "Hint: pass full live URL (uses web enter API), ensure room is live, "
                "session valid; Playwright needs PLAYWRIGHT_BROWSERS_PATH."
            )
        print(f"[resolve] flv pull ok ({stream_url[:48]}...)")

    rc = run_streaming_stt(
        stream_url=stream_url,
        api_key=args.api_key.strip(),
        model=args.model,
        language=args.language,
        duration_sec=args.duration,
        smart_format=not args.no_smart_format,
        ffmpeg=args.ffmpeg,
    )
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
