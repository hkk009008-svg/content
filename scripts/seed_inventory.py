#!/usr/bin/env python3
"""Enumerate existing pytest xfail pins under a tests/ tree → candidate inventory rows.

Emits to stdout; never writes the inventory (coordinator is the single writer, spec §2).
Uses the AST so it is robust to formatting. Captures reason + strict for each xfail mark.
"""
from __future__ import annotations
import argparse
import ast
import sys
from pathlib import Path

def _xfail_marks(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # Matches any `*.xfail(...)` Attribute-call (covers pytest.mark.xfail and mark.xfail).
        # Broad by design; a tests/ tree has no unrelated .xfail() calls (verified).
        if isinstance(f, ast.Attribute) and f.attr == "xfail":
            yield node

def find_xfail_pins(tests_root: Path) -> list[dict]:
    pins: list[dict] = []
    for path in sorted(Path(tests_root).rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for call in _xfail_marks(tree):
            reason, strict = "", False
            # Only literal (ast.Constant) reason=/strict= are captured; an f-string or
            # variable expression is silently skipped (reason="" / strict=False). All
            # current pins use literal strings, so this is a non-issue in practice.
            for kw in call.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    reason = str(kw.value.value)
                if kw.arg == "strict" and isinstance(kw.value, ast.Constant):
                    strict = bool(kw.value.value)
            pins.append({"test_file": str(path), "reason": reason, "strict": strict})
    return pins

def _slug(reason: str) -> str:
    # "W1:CRITICAL:budget-nan core.py:101 ..." -> "budget-nan" when prefixed, else first token
    parts = reason.split()
    head = parts[0] if parts else "unknown"
    if head.count(":") >= 2:
        return head.split(":")[2]
    return (head[:32] or "unknown")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tests", default="tests", type=Path)
    args = ap.parse_args(argv)
    seen: dict[str, int] = {}
    for p in find_xfail_pins(args.tests):
        flag = "strict" if p["strict"] else "NON-STRICT"
        sid = _slug(p["reason"])
        seen[sid] = seen.get(sid, 0) + 1
        if seen[sid] > 1:
            sid = f"{sid}-{seen[sid]}"   # de-collide duplicate slugs (e.g. two 'sibling' pins)
        print(f"| {sid} |  |  |  |  |  |  | {p['test_file']} |  |  |  | open |  | {flag}: {p['reason'][:60]} |")
    return 0

if __name__ == "__main__":
    sys.exit(main())
