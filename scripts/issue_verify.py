#!/usr/bin/env python3
"""Run verification commands from docs/issues/*.md (orchestrator + CI)."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "docs" / "issues"

SKIP_PREFIXES = (
    "source ",
    "pip install ",
    "pnpm install",
    "cd ",
)


def find_issue_md(*, issue: int | None = None, slug: str | None = None, branch: str | None = None) -> Path:
    if slug:
        path = Path(slug)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            return path
        raise SystemExit(f"Issue file not found: {slug}")

    if branch:
        m = re.match(r"issue-(\d+)-", branch)
        if m:
            issue = int(m.group(1))

    if issue is None:
        raise SystemExit("Need --issue, --slug, --branch issue-N-*, or --from-pr with Fixes #N")

    needle = f"#{issue}"
    matches: list[Path] = []
    for path in sorted(ISSUES_DIR.glob("*.md")):
        if path.name.startswith("_") or path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        if (
            f"GitHub Issue: [{needle}]" in text
            or f"GitHub Issue: {needle}" in text
            or re.search(rf"^-\s+GitHub Issue:\s+\[{needle}\]", text, re.M)
        ):
            matches.append(path)
            continue
        # fallback: issue number in 实现备注 / frontmatter github field
        if re.search(rf"^github:\s*{issue}\s*$", text, re.M):
            matches.append(path)

    if not matches:
        raise SystemExit(f"No docs/issues/*.md references issue {issue}")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise SystemExit(f"Ambiguous issue {issue}: {names}")
    return matches[0]


def extract_verify_block(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8")
    m = re.search(
        r"^##\s+验证命令\s*\n+```(?:bash|sh)\n(.*?)```",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise SystemExit(f"No ## 验证命令 bash block in {md_path}")
    return m.group(1).strip()


def split_commands(block: str) -> list[str]:
    lines: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if any(line.startswith(p) for p in SKIP_PREFIXES):
            continue
        lines.append(line)
    return lines


def run_command(cmd: str, *, dry_run: bool) -> int:
    print(f"\n$ {cmd}")
    if dry_run:
        return 0
    proc = subprocess.run(cmd, shell=True, cwd=ROOT, check=False)
    return proc.returncode


def issue_from_pr(pr: int) -> int:
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", "body,headRefName"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"gh pr view failed: {proc.stderr.strip()}")
    import json

    data = json.loads(proc.stdout)
    body = data.get("body") or ""
    m = re.search(r"(?:Fixes|Closes)\s+#(\d+)", body, re.I)
    if m:
        return int(m.group(1))
    branch = data.get("headRefName") or ""
    m2 = re.match(r"issue-(\d+)-", branch)
    if m2:
        return int(m2.group(1))
    raise SystemExit(f"Cannot resolve issue number from PR #{pr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Issue verification commands from docs/issues/*.md")
    parser.add_argument("--issue", type=int, help="GitHub issue number")
    parser.add_argument("--slug", help="Path to docs/issues/*.md")
    parser.add_argument("--branch", help="Git branch name (issue-N-slug)")
    parser.add_argument("--from-pr", type=int, dest="from_pr", help="GitHub PR number (needs gh)")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    args = parser.parse_args()

    issue = args.issue
    if args.from_pr:
        issue = issue_from_pr(args.from_pr)

    md_path = find_issue_md(issue=issue, slug=args.slug, branch=args.branch)
    block = extract_verify_block(md_path)
    commands = split_commands(block)

    print(f"Issue doc: {md_path.relative_to(ROOT)}")
    if not commands:
        print("No runnable commands after filtering setup lines.", file=sys.stderr)
        return 1

    failed = 0
    for cmd in commands:
        code = run_command(cmd, dry_run=args.dry_run)
        if code != 0:
            print(f"FAILED (exit {code}): {cmd}", file=sys.stderr)
            failed += 1
            if not args.dry_run:
                return code

    if failed:
        return 1
    print("\nissue_verify: all commands passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
