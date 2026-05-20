#!/usr/bin/env python3
"""Minimal reproduction of Deepgram official streaming sample."""

from __future__ import annotations

import sys
import threading
import time

import httpx
from deepgram import DeepgramClient
from deepgram.core.events import EventType

API_KEY = sys.argv[1] if len(sys.argv) > 1 else ""
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
LANGUAGE = sys.argv[3] if len(sys.argv) > 3 else "zh"
STREAM_URL = (
    "https://playerservices.streamtheworld.com/api/livestream-redirect/CSPANRADIOAAC.aac"
)

if not API_KEY:
    sys.exit("usage: test_deepgram_sdk_official.py <api_key> [duration_sec] [language]")

client = DeepgramClient(api_key=API_KEY)

with client.listen.v1.connect(
    model="nova-3",
    language=LANGUAGE,
    smart_format=True,
    diarize=True,
) as connection:
    ready = threading.Event()
    stop_at = time.monotonic() + DURATION

    def on_message(result):
        channel = getattr(result, "channel", None)
        if channel and hasattr(channel, "alternatives"):
            transcript = channel.alternatives[0].transcript
            words = channel.alternatives[0].words or []
            speakers = {w.speaker for w in words if hasattr(w, "speaker") and w.speaker is not None}
            speaker = None
            if words and hasattr(words[0], "speaker") and words[0].speaker is not None:
                speaker = f"{words[0].speaker}+" if len(speakers) > 1 else words[0].speaker
            if transcript:
                print(f"[Speaker {speaker}] {transcript}", flush=True)

    connection.on(EventType.OPEN, lambda _: ready.set())
    connection.on(EventType.MESSAGE, on_message)
    connection.on(EventType.ERROR, lambda e: print(f"[error] {e}", flush=True))

    def stream():
        ready.wait()
        with httpx.stream("GET", STREAM_URL, follow_redirects=True, timeout=30.0) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if time.monotonic() >= stop_at:
                    break
                if chunk:
                    connection.send_media(chunk)

    threading.Thread(target=stream, daemon=True).start()
    print(f"Transcribing {STREAM_URL} (nova-3, language={LANGUAGE}, {DURATION}s)...", flush=True)
    connection.start_listening()
