#!/usr/bin/env python3
"""Run Epic-level verification from docs/issues/epic-manifests/*.yaml."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "docs" / "issues" / "epic-manifests"


def load_manifest(name: str) -> dict:
    path = MANIFEST_DIR / f"{name}.yaml"
    if not path.is_file():
        raise SystemExit(f"Epic manifest not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_step(step: dict, *, dry_run: bool) -> tuple[bool, str]:
    label = step.get("name") or step.get("run", "?")
    cmd = step["run"]
    optional = bool(step.get("optional"))
    print(f"\n== {label} ==")
    print(f"$ {cmd}")
    if dry_run:
        return True, "dry-run"
    proc = subprocess.run(cmd, shell=True, cwd=ROOT, check=False)
    if proc.returncode == 0:
        return True, "pass"
    if optional:
        print(f"optional step failed (exit {proc.returncode}), continuing", file=sys.stderr)
        return True, "optional-fail"
    return False, f"exit {proc.returncode}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Epic verification manifest")
    parser.add_argument("epic", help="Manifest basename, e.g. agent-hermes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    args = parser.parse_args()

    manifest = load_manifest(args.epic)
    print(f"Epic: {manifest.get('name', args.epic)}")
    if spec := manifest.get("spec"):
        print(f"Spec: {spec}")

    results: list[dict] = []
    ok = True
    for step in manifest.get("steps", []):
        passed, detail = run_step(step, dry_run=args.dry_run)
        results.append({"name": step.get("name"), "ok": passed, "detail": detail})
        if not passed:
            ok = False
            break

    if args.json:
        import json

        print(json.dumps({"epic": args.epic, "ok": ok, "steps": results}, ensure_ascii=False, indent=2))

    if ok:
        print(f"\nepic_verify: {args.epic} PASS")
        return 0
    print(f"\nepic_verify: {args.epic} FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
