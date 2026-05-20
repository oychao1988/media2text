#!/usr/bin/env python3
"""Official SDK pattern — local file via ffmpeg AAC pipe."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from deepgram import DeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

API_KEY = sys.argv[1]
INPUT = sys.argv[2]
DURATION = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0

client = DeepgramClient(api_key=API_KEY)

with client.listen.v1.connect(
    model="nova-3",
    language="zh",
    smart_format=True,
    punctuate=True,
    interim_results=True,
) as connection:
    ready = threading.Event()

    def on_message(result):
        if isinstance(result, ListenV1Results):
            alt = result.channel.alternatives[0]
            if alt.transcript:
                tag = "final" if result.is_final else "interim"
                print(f"[{tag}] {alt.transcript}", flush=True)
        else:
            print(f"[other] {type(result).__name__}", flush=True)

    connection.on(EventType.OPEN, lambda _: ready.set())
    connection.on(EventType.MESSAGE, on_message)
    connection.on(EventType.ERROR, lambda e: print(f"[error] {e}", flush=True))

    def stream():
        ready.wait()
        cmd = [
            "ffmpeg", "-loglevel", "error", "-i", INPUT,
            "-t", str(DURATION), "-vn", "-c:a", "aac", "-b:a", "128k", "-f", "adts", "-",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        assert proc.stdout
        for chunk in iter(lambda: proc.stdout.read(4096), b""):
            connection.send_media(chunk)
        proc.wait()

    threading.Thread(target=stream, daemon=True).start()
    print(f"Transcribing {INPUT} ...", flush=True)
    connection.start_listening()
