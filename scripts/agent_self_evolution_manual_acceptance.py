#!/usr/bin/env python3
"""Run agent-self-evolution manual acceptance (S10, S15) via isolated mock integration tests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".tmp/agent-self-evolution-manual-acceptance.json"
JUNIT = ROOT / ".tmp/agent-self-evolution-manual-junit.xml"
TEST_FILE = "tests/unit/test_agent_self_evolution_manual_acceptance.py"


def _parse_junit(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    root = ET.parse(path).getroot()
    cases: list[dict] = []
    for suite in root.iter("testsuite"):
        for case in suite.iter("testcase"):
            name = case.get("name") or ""
            failed = case.find("failure") is not None or case.find("error") is not None
            entry = {
                "test": name,
                "pass": not failed,
            }
            if failed:
                node = case.find("failure") or case.find("error")
                entry["detail"] = (node.text or "").strip() if node is not None else "failed"
            cases.append(entry)
    return cases


def _map_results(cases: list[dict]) -> list[dict]:
    mapping = {
        "test_s10_review_patches_distill_perspective_pitfall": (
            "S10",
            "review patch distill perspective pitfall 段",
        ),
        "test_s15_curator_rollback_restores_backup": (
            "S15",
            "curator rollback 恢复备份",
        ),
    }
    out: list[dict] = []
    for case in cases:
        test_name = case["test"]
        sid, label = mapping.get(test_name, (test_name, test_name))
        out.append(
            {
                "id": sid,
                "name": label,
                "pass": case["pass"],
                "detail": case.get("detail", "ok" if case["pass"] else "failed"),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent self-evolution manual acceptance (S10, S15)")
    parser.add_argument("--pytest-args", default="", help="Extra args passed to pytest")
    args = parser.parse_args()

    JUNIT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        TEST_FILE,
        "-v",
        "--tb=short",
        f"--junitxml={JUNIT}",
    ]
    if args.pytest_args.strip():
        cmd.extend(args.pytest_args.split())

    print(f"== Running {TEST_FILE} ==")
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    cases = _parse_junit(JUNIT)
    results = _map_results(cases)

    if not results:
        results = [
            {
                "id": "S10/S15",
                "name": "manual acceptance tests",
                "pass": proc.returncode == 0,
                "detail": f"pytest exit={proc.returncode}; junit missing or empty",
            }
        ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": proc.returncode,
        "all_pass": proc.returncode == 0 and all(r["pass"] for r in results),
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for row in results:
        status = "PASS" if row["pass"] else "FAIL"
        print(f"  [{status}] {row['id']}: {row['name']}")
        if not row["pass"] and row.get("detail"):
            print(f"         {row['detail'][:200]}")

    print(f"\nReport: {REPORT}")
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
