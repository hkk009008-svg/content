#!/usr/bin/env python3
"""Report verified inventory rows whose pins still behave like xfail pins.

ADR-027 keeps "verified" tied to a live regression. This read-only checker runs
verified-row selectors normally, without --runxfail, and reports selectors that
still emit xfail/xpass state or fail outright. By default it reports only; pass
--strict to make findings fail the process.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

from wave_gate_check import _REPO_ROOT, _dedupe, _parse_rows, _selectors_from_pin

_XFAIL_SIGNAL_RE = re.compile(r"\b(?:XFAIL|XPASS|xfailed|xpassed)\b")

Runner = Callable[[list[str]], dict]


def _run_pytest_normal(selectors: list[str]) -> dict:
    args = [sys.executable, "-m", "pytest", *selectors, "-q", "--tb=short"]
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    proc = subprocess.run(
        args,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "args": args,
        "command": shlex.join(args),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _has_xfail_signal(result: dict) -> bool:
    return bool(_XFAIL_SIGNAL_RE.search(
        f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    ))


def reconcile_report(
    inventory_path: Path,
    *,
    wave: int | None = None,
    runner: Runner | None = None,
) -> dict:
    rows = [r for r in _parse_rows(inventory_path) if r["status"] == "verified"]
    if wave is not None:
        rows = [r for r in rows if r["wave"] == str(wave)]

    missing: list[dict] = []
    results: list[dict] = []
    run = runner or _run_pytest_normal

    for row in rows:
        selectors = _selectors_from_pin(row["xfail-pin"])
        if not selectors:
            missing.append({**row, "issue": "verified row has no executable selector"})
            continue
        selectors = _dedupe(selectors)
        result = run(selectors)
        has_xfail = _has_xfail_signal(result)
        issue = None
        if result["exit_code"] != 0:
            issue = "normal pytest failed"
        elif has_xfail:
            issue = "normal pytest still reports xfail/xpass state"
        results.append({
            "row": row,
            "selectors": selectors,
            "pytest": result,
            "issue": issue,
            "has_xfail_signal": has_xfail,
        })

    return {
        "wave": wave,
        "rows": rows,
        "missing": missing,
        "results": results,
        "issues": [r for r in results if r["issue"]] + missing,
    }


def _tail(text: str, max_lines: int = 12) -> list[str]:
    lines = text.rstrip().splitlines()
    if len(lines) <= max_lines:
        return lines
    return ["..."] + lines[-max_lines:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inventory", default=_REPO_ROOT / "docs/REMEDIATION-INVENTORY.md", type=Path)
    ap.add_argument("--wave", type=int)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when stale/missing verified-row pins are found.",
    )
    args = ap.parse_args(argv)

    if not args.inventory.exists():
        print(f"inventory not found: {args.inventory}", file=sys.stderr)
        return 2

    rep = reconcile_report(args.inventory, wave=args.wave)
    scope = f"wave {args.wave}" if args.wave is not None else "all waves"
    print(f"Pin reconciler: {scope}; verified rows={len(rep['rows'])}; issues={len(rep['issues'])}")

    for missing in rep["missing"]:
        print(f"  MISSING [{missing['wave']}] {missing['id']}: {missing['issue']}")

    for item in rep["results"]:
        row = item["row"]
        status = "ISSUE" if item["issue"] else "clean"
        print(f"  {status} [{row['wave']}] {row['id']}: {', '.join(item['selectors'])}")
        if item["issue"]:
            print(f"    reason: {item['issue']}; exit={item['pytest']['exit_code']}")
            for line in _tail(item["pytest"].get("stdout", "")):
                print(f"    {line}")
            for line in _tail(item["pytest"].get("stderr", "")):
                print(f"    {line}")

    return 1 if args.strict and rep["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
