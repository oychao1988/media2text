#!/usr/bin/env python3
"""Measure OpenClaw Gateway chat latency (TTFB / TTFT / total)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_token() -> str:
    env_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_token:
        return env_token
    config_path = os.environ.get(
        "OPENCLAW_CONFIG_PATH",
        str(Path.home() / ".openclaw" / "openclaw.json"),
    )
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    token = data.get("gateway", {}).get("auth", {}).get("token")
    if not token:
        raise SystemExit(f"gateway.auth.token missing in {config_path}")
    return str(token)


def run_once(
    *,
    url: str,
    token: str,
    session_key: str,
    message: str,
    stream: bool,
    thinking: str | None,
    fast: bool | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "openclaw",
        "stream": stream,
        "session_key": session_key,
        "messages": [{"role": "user", "content": message}],
    }
    if thinking is not None:
        body["thinking"] = thinking
    if fast is not None:
        body["fast"] = fast

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            **({"Accept": "text/event-stream"} if stream else {}),
        },
        method="POST",
    )

    t0 = time.perf_counter()
    ttfb_ms: float | None = None
    ttft_ms: float | None = None
    total_ms: float | None = None
    first_text = ""

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            ttfb_ms = (time.perf_counter() - t0) * 1000
            if not stream:
                raw = resp.read()
                total_ms = (time.perf_counter() - t0) * 1000
                data = json.loads(raw)
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if content:
                    ttft_ms = total_ms
                    first_text = str(content)[:80]
                return {
                    "ok": True,
                    "ttfb_ms": round(ttfb_ms, 1),
                    "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                    "total_ms": round(total_ms, 1),
                    "first_text": first_text,
                }

            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    total_ms = (time.perf_counter() - t0) * 1000
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content") or ""
                if content and ttft_ms is None:
                    ttft_ms = (time.perf_counter() - t0) * 1000
                    first_text = str(content)[:80]
            if total_ms is None:
                total_ms = (time.perf_counter() - t0) * 1000
            return {
                "ok": True,
                "ttfb_ms": round(ttfb_ms or 0, 1),
                "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                "total_ms": round(total_ms, 1),
                "first_text": first_text,
            }
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:500]
        return {
            "ok": False,
            "error": f"HTTP {err.code}: {detail}",
            "ttfb_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except urllib.error.URLError as err:
        return {
            "ok": False,
            "error": str(err.reason or err),
            "ttfb_ms": None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OpenClaw chat latency")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="JSON output (default)")
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "OPENCLAW_GATEWAY_HTTP",
            "http://127.0.0.1:18789/v1/chat/completions",
        ),
    )
    parser.add_argument("--session-key", default="agent:main:main")
    parser.add_argument("--message", default="回复一个字：好")
    parser.add_argument(
        "--thinking",
        choices=["off", "low", "medium", "high"],
        default=None,
    )
    parser.add_argument("--fast", action="store_true")
    parser.add_argument(
        "--mode",
        choices=["agent", "fast"],
        default=None,
        help="Chat mode preset: agent (default lens session) or fast (thinking=off, fast session)",
    )
    parser.add_argument("--no-stream", action="store_true")
    args = parser.parse_args()

    try:
        token = load_token()
    except (OSError, json.JSONDecodeError, KeyError) as err:
        print(json.dumps({"ok": False, "error": str(err)}), file=sys.stderr)
        return 1

    stream = not args.no_stream

    session_key = args.session_key
    thinking = args.thinking
    fast: bool | None = True if args.fast else None

    if args.mode == "fast":
        session_key = "agent:main:fast"
        thinking = "off"
        fast = True
    elif args.mode == "agent":
        thinking = None
        fast = None

    if thinking == "off" and fast is None:
        fast = True
    if args.fast and fast is None:
        fast = True

    runs: list[dict[str, Any]] = []
    failures = 0
    for i in range(args.runs):
        result = run_once(
            url=args.url,
            token=token,
            session_key=session_key,
            message=args.message,
            stream=stream,
            thinking=thinking,
            fast=fast,
        )
        result["run"] = i + 1
        result["session_key"] = session_key
        result["stream"] = stream
        result["thinking"] = thinking
        result["mode"] = args.mode
        runs.append(result)
        if not result.get("ok"):
            failures += 1

    ttfts = [r["ttft_ms"] for r in runs if r.get("ok") and r.get("ttft_ms") is not None]
    summary = {
        "ok": failures == 0,
        "runs": runs,
        "url": args.url,
        "stream": stream,
        "thinking": thinking,
        "mode": args.mode,
        "session_key": session_key,
        "failures": failures,
        "ttft_ms_p50": round(sorted(ttfts)[len(ttfts) // 2], 1) if ttfts else None,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures == len(runs):
        return 1
    if failures:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
