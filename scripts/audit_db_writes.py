#!/usr/bin/env python3
"""Fail CI if WriteAwareRepo mutators commit outside gateway _mutate wrappers (DL-4d)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPOS_PKG = ROOT / "src/media2text/core/storage/repos"

SCAN_FILES = [
    ROOT / "src/media2text/core/live/state_writer.py",
    *sorted(REPOS_PKG.glob("*.py")),
]

WRITE_AWARE_BASE = "WriteAwareRepo"


def _is_conn_commit(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "commit"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "_conn"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    )


def _mutate_nested_names(method: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "_mutate"
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            continue
        if len(node.args) < 2:
            continue
        inner = node.args[1]
        if isinstance(inner, ast.Name):
            names.add(inner.id)
    return names


def _direct_commits(method: ast.FunctionDef) -> list[int]:
    allowed_nested = _mutate_nested_names(method)
    violations: list[int] = []

    def visit(node: ast.AST, *, in_allowed_nested: bool) -> None:
        if isinstance(node, ast.FunctionDef):
            allowed = in_allowed_nested or node.name in allowed_nested
            for child in node.body:
                visit(child, in_allowed_nested=allowed)
            return
        if _is_conn_commit(node) and not in_allowed_nested:
            violations.append(node.lineno)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, in_allowed_nested=in_allowed_nested)

    for stmt in method.body:
        visit(stmt, in_allowed_nested=False)
    return violations


def _write_aware_classes(tree: ast.Module) -> set[str]:
    classes: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = None
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            if name == WRITE_AWARE_BASE:
                classes.add(node.name)
                break
    return classes


def audit_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    rel = path.relative_to(ROOT)
    violations: list[str] = []
    targets = _write_aware_classes(tree)
    if path.name == "state_writer.py":
        targets.add("StateWriter")

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in targets:
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            for lineno in _direct_commits(item):
                violations.append(
                    f"{rel}:{lineno}: bare self._conn.commit() in {node.name}.{item.name}"
                )
    return violations


def main() -> int:
    all_violations: list[str] = []
    for path in SCAN_FILES:
        if not path.is_file():
            all_violations.append(f"missing scan file: {path}")
            continue
        all_violations.extend(audit_file(path))

    if all_violations:
        print("Bare DB commits outside WriteAwareRepo._mutate:")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("OK: WriteAwareRepo mutators route commits through _mutate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
