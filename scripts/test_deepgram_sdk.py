#!/usr/bin/env python3
"""Test Deepgram official Python SDK (listen.v1.connect) — stream URL or local file."""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results


def run_stream(
    *,
    api_key: str,
    source: str,
    model: str,
    language: str,
    duration_sec: float,
    smart_format: bool,
    diarize: bool,
    is_url: bool,
) -> None:
    client = DeepgramClient(api_key=api_key)

    with client.listen.v1.connect(
        model=model,
        language=language,
        smart_format=smart_format,
        diarize=diarize,
    ) as connection:
        ready = threading.Event()
        done = threading.Event()
        lines: list[str] = []
        debug_left = 3

        def on_message(result) -> None:
            nonlocal debug_left
            if debug_left > 0 and not isinstance(result, ListenV1Results):
                debug_left -= 1
                print(f"[debug] {type(result).__name__}: {result!r}"[:300], flush=True)

            if not isinstance(result, ListenV1Results):
                return

            channel = result.channel
            is_final = result.is_final if result.is_final is not None else True
            if not channel.alternatives:
                return
            alt = channel.alternatives[0]
            transcript = alt.transcript or ""
            if not transcript:
                return
            words = alt.words or []
            speakers = {w.speaker for w in words if w.speaker is not None}
            speaker = None
            if words and words[0].speaker is not None:
                speaker = f"{words[0].speaker}+" if len(speakers) > 1 else words[0].speaker
            tag = "final" if is_final else "interim"
            prefix = f"[{tag}]"
            if speaker is not None:
                prefix += f" [Speaker {speaker}]"
            line = f"{prefix} {transcript}"
            print(line, flush=True)
            if is_final:
                lines.append(transcript)

        connection.on(EventType.OPEN, lambda _: ready.set())
        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.CLOSE, lambda _: done.set())
        connection.on(EventType.ERROR, lambda err: print(f"[error] {err}", file=sys.stderr))

        def stream_url() -> None:
            ready.wait()
            deadline = time.monotonic() + duration_sec
            with httpx.stream("GET", source, follow_redirects=True, timeout=30.0) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= deadline:
                        break
                    if chunk:
                        connection.send_media(chunk)
            connection.send_close_stream()

        def stream_file() -> None:
            ready.wait()
            # Re-encode to AAC (ADTS) chunks — same container style as the CSPAN sample stream.
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                source,
                "-t",
                str(duration_sec),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "adts",
                "-",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert proc.stdout is not None
            try:
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    connection.send_media(chunk)
            finally:
                proc.wait(timeout=15)
            connection.send_close_stream()

        feeder = threading.Thread(
            target=stream_url if is_url else stream_file,
            daemon=True,
        )

        label = source if is_url else Path(source).name
        print(f"Transcribing {label} (model={model}, language={language}, {duration_sec}s)...")
        # Match official sample: block on start_listening in main thread.
        listen_deadline = time.time() + duration_sec + 20
        listen_thread = threading.Thread(target=connection.start_listening, daemon=True)
        listen_thread.start()
        while feeder.is_alive() and time.time() < listen_deadline:
            time.sleep(0.2)
        if listen_thread.is_alive():
            time.sleep(5)

        print("--- done ---")
        if lines:
            print("--- final merge (first 400 chars) ---")
            merged = " ".join(lines)
            print(merged[:400] + ("..." if len(merged) > 400 else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="HTTP(S) stream URL or local media path")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="nova-3")
    parser.add_argument("--language", default="zh")
    parser.add_argument("-t", "--duration", type=float, default=25.0)
    parser.add_argument("--no-smart-format", action="store_true")
    parser.add_argument("--no-diarize", action="store_true")
    args = parser.parse_args()

    is_url = args.source.startswith("http://") or args.source.startswith("https://")
    if not is_url and not Path(args.source).exists():
        sys.exit(f"file not found: {args.source}")

    run_stream(
        api_key=args.api_key,
        source=args.source,
        model=args.model,
        language=args.language,
        duration_sec=args.duration,
        smart_format=not args.no_smart_format,
        diarize=not args.no_diarize,
        is_url=is_url,
    )


if __name__ == "__main__":
    main()
