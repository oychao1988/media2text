#!/usr/bin/env python3
"""Run M2 (#182) verification aligned with issue spec + Hermes H8/H9/H2."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_RS = ROOT / "apps/m2t-desktop/src-tauri/src/lib.rs"
REPORT = ROOT / ".tmp/m2-verification-report.json"


def run(cmd: list[str], *, cwd: Path = ROOT) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def static_h8_no_node_agent_spawn() -> dict:
    text = LIB_RS.read_text(encoding="utf-8")
    forbidden = ["agent_sidecar", "start-sidecar", "m2t-agent-sidecar"]
    hits = [f for f in forbidden if f in text]
    return {
        "name": "H8 static: lib.rs has no Node agent sidecar spawn",
        "pass": len(hits) == 0,
        "detail": "forbidden refs in lib.rs: " + (", ".join(hits) if hits else "none"),
    }


def live_ws_ready(port: int) -> dict:
    """Start serve briefly; assert health + WS sidecar.ready (no LLM turn)."""
    serve = subprocess.Popen(
        [sys.executable, "-m", "media2text", "serve", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    health_url = f"http://127.0.0.1:{port}/api/health"
    ok = False
    err = ""
    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen(health_url, timeout=1) as resp:
                    if resp.status == 200:
                        ok = True
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        if not ok:
            err = "health never ready"
        else:
            # websocket via websockets if available; else skip with note
            try:
                import websockets.sync.client as wsc  # type: ignore[import-untyped]

                with wsc.connect(f"ws://127.0.0.1:{port}/api/agent/stream") as ws:
                    msg = json.loads(ws.recv(timeout=5))
                    if msg.get("type") != "sidecar.ready":
                        err = f"expected sidecar.ready, got {msg.get('type')}"
                        ok = False
            except ImportError:
                err = "websockets not installed; health-only smoke"
    finally:
        serve.terminate()
        try:
            serve.wait(timeout=5)
        except subprocess.TimeoutExpired:
            serve.kill()
        if serve.stderr:
            tail = serve.stderr.read()[-500:]
            if not ok and tail:
                err = (err + " | stderr: " + tail).strip(" |")
    return {
        "name": "live serve health + WS ready",
        "pass": ok,
        "detail": err or "health 200 + sidecar.ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-port", type=int, default=9876)
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Only run H8 static check (no issue #182 / pnpm / cargo)",
    )
    args = parser.parse_args()

    results: list[dict] = []

    if args.static_only:
        results.append(static_h8_no_node_agent_spawn())
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "issue": "static-only",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "all_pass": all(r["pass"] for r in results),
            "results": results,
        }
        REPORT.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Report: {REPORT}")
        for r in results:
            status = "PASS" if r["pass"] else "FAIL"
            print(f"  [{status}] {r['name']}")
        return 0 if payload["all_pass"] else 1

    steps = [
        (["python", "scripts/issue_verify.py", "--issue", "182"], "issue_verify #182"),
        (
            [
                "pytest",
                "tests/unit/test_api_agent_m2_smoke.py",
                "tests/unit/test_api_agent_stream.py",
                "tests/unit/test_api_agent_threads.py",
                "-v",
                "-m",
                "desktop",
            ],
            "pytest agent M2 smoke",
        ),
        (["pnpm", "--filter", "m2t-desktop", "test"], "vitest m2t-desktop"),
        (["cargo", "check"], "cargo check tauri"),
    ]

    for cmd, label in steps:
        if label.startswith("cargo"):
            code, out = run(cmd, cwd=ROOT / "apps/m2t-desktop/src-tauri")
        else:
            code, out = run(cmd)
        tail = out.strip()[-1200:] if out else ""
        results.append({"name": label, "pass": code == 0, "exit_code": code, "tail": tail})

    results.append(static_h8_no_node_agent_spawn())

    if not args.skip_live:
        results.append(live_ws_ready(args.live_port))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "issue": 182,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_pass": all(r["pass"] for r in results),
        "results": results,
    }
    REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Report: {REPORT}")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['name']}")
        if not r["pass"] and r.get("tail"):
            print(r["tail"][-400:])
        if not r["pass"] and r.get("detail"):
            print("   ", r["detail"])

    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
