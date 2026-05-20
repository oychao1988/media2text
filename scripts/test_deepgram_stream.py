#!/usr/bin/env python3
"""Quick test for Deepgram v2 streaming (flux) — mirrors the websocat reference flow."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
from pathlib import Path

import websockets


def ffmpeg_audio_pipe(input_path: str, duration_sec: float | None) -> subprocess.Popen[bytes]:
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        input_path,
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(duration_sec)])
    cmd.extend(["-f", "s16le", "-ar", "16000", "-ac", "1", "-"])
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


async def stream_transcribe(
    *,
    input_path: str,
    api_key: str,
    endpoint: str,
    duration_sec: float | None,
    chunk_bytes: int = 3200,
) -> int:
    headers = {"Authorization": f"Token {api_key}"}
    proc = ffmpeg_audio_pipe(input_path, duration_sec)

    async with websockets.connect(
        endpoint,
        additional_headers=headers,
        max_size=None,
    ) as ws:
        async def send_audio() -> None:
            assert proc.stdout is not None
            try:
                while True:
                    chunk = proc.stdout.read(chunk_bytes)
                    if not chunk:
                        break
                    await ws.send(chunk)  # binary linear16 per Deepgram docs
            finally:
                await ws.send(json.dumps({"type": "CloseStream"}))

        async def recv_messages() -> None:
            async for msg in ws:
                if not msg:
                    continue
                if isinstance(msg, bytes):
                    try:
                        data = json.loads(msg.decode("utf-8"))
                    except Exception:
                        print(f"[binary] {len(msg)} bytes", file=sys.stderr)
                        continue
                else:
                    data = json.loads(msg)

                msg_type = data.get("type") or ""
                if msg_type == "Connected":
                    print(f"[connected] request_id={data.get('request_id')}")
                    continue
                if msg_type == "Error":
                    print(
                        f"[error] {data.get('code')}: {data.get('description')}",
                        file=sys.stderr,
                    )
                    continue

                event = data.get("event") or ""
                turn_index = data.get("turn_index")
                transcript = data.get("transcript") or ""
                eot_confidence = data.get("end_of_turn_confidence")

                if event == "StartOfTurn":
                    print(f"--- StartOfTurn (Turn {turn_index}) ---")
                if transcript:
                    print(transcript)
                if event == "EndOfTurn":
                    print(
                        f"--- EndOfTurn (Turn {turn_index}, Confidence: {eot_confidence}) ---"
                    )
                if msg_type == "TurnInfo" and transcript and not event:
                    langs = data.get("languages")
                    suffix = f" [{langs}]" if langs else ""
                    print(f"{transcript}{suffix}")

        send_task = asyncio.create_task(send_audio())
        recv_task = asyncio.create_task(recv_messages())
        await send_task
        try:
            await asyncio.wait_for(recv_task, timeout=15)
        except asyncio.TimeoutError:
            recv_task.cancel()

    proc.wait(timeout=5)
    if proc.stderr:
        err = proc.stderr.read().decode("utf-8", errors="replace").strip()
        if err:
            print(f"[ffmpeg stderr] {err}", file=sys.stderr)
    return proc.returncode or 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Audio/video file path")
    parser.add_argument("--api-key", required=True)
    parser.add_argument(
        "--endpoint",
        default=(
            "wss://api.deepgram.com/v2/listen"
            "?eot_threshold=0.7&eot_timeout_ms=5000"
            "&model=flux-general-en&encoding=linear16&sample_rate=16000"
        ),
    )
    parser.add_argument("-t", "--duration", type=float, default=45.0)
    args = parser.parse_args()

    if not Path(args.input).exists():
        sys.exit(f"file not found: {args.input}")

    rc = asyncio.run(
        stream_transcribe(
            input_path=args.input,
            api_key=args.api_key,
            endpoint=args.endpoint,
            duration_sec=args.duration,
        )
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
