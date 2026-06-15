#!/usr/bin/env python3
"""Executable wave-gate checker for the hardening campaign.

Reads docs/REMEDIATION-INVENTORY.md and reports, for a wave, whether the gate is
MET. ADR-027 makes the inventory status column display-only for this verdict:
the gate executes the wave's CRITICAL/MAJOR pins with pytest --runxfail and
fails closed on missing/non-executable oracles.

Read-only - never mutates the inventory.
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import math
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent

_COLS = ("id", "subsystem", "file:line", "severity", "priority", "fail-mode",
         "repro", "xfail-pin", "lane-owner", "shared-lock", "wave", "status",
         "verifier", "notes")
_BLOCK_SEV = {"CRITICAL", "MAJOR"}
_SELECTOR_RE = re.compile(
    r"(?P<selector>(?:\.?/)?tests/[A-Za-z0-9_./-]+\.py(?:::[^\s;,()]+)*)"
)
_XFAIL_SIGNAL_RE = re.compile(r"\b(?:XFAIL|XPASS|xfailed|xpassed)\b")
_PRODUCT_ORACLE_MIN_WAVE = 2
_PRODUCT_ORACLE_PATTERN = "logs/product-oracle-*.json"

PytestRunner = Callable[[list[str]], dict]

def _parse_rows(inventory_path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in inventory_path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(_COLS):           # header / separator / malformed / pipe-in-value
            continue
        row = dict(zip(_COLS, cells))
        if row["id"] in ("id", "----", "") or set(row["id"]) <= {"-"}:
            continue
        rows.append(row)
    return rows

def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out

def _selectors_from_pin(pin_cell: str) -> list[str]:
    """Extract executable pytest selectors from an inventory xfail-pin cell."""
    selectors: list[str] = []
    last_path: str | None = None
    pieces = re.split(r"\s+/\s+|[;,]\s*", pin_cell.strip())
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if piece.startswith("::") and last_path:
            node = piece.split()[0].rstrip(").,;")
            selectors.append(f"{last_path}{node}")
            continue
        for match in _SELECTOR_RE.finditer(piece):
            selector = match.group("selector").rstrip(").,;")
            selectors.append(selector)
            last_path = selector.split("::", 1)[0]
    return _dedupe(selectors)

def _gate_row(row: dict) -> bool:
    return row["severity"].upper() in _BLOCK_SEV or row["status"] == "provisional"

def _blocker(row: dict, reason: str) -> dict:
    blocked = dict(row)
    blocked["block_reason"] = reason
    return blocked

def _run_pytest_selectors(selectors: list[str]) -> dict:
    args = [
        sys.executable,
        "-m",
        "pytest",
        *selectors,
        "--runxfail",
        "-q",
        "--tb=short",
    ]
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

def _committed_product_oracle_paths() -> tuple[list[Path], str | None]:
    """Return product-oracle artifacts committed in HEAD, ignoring seat-local indexes."""
    args = [
        "git",
        "ls-tree",
        "-r",
        "--name-only",
        "HEAD",
        "--",
        "logs",
    ]
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    try:
        proc = subprocess.run(
            args,
            cwd=_REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return [], str(exc)
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or "git ls-tree failed").strip()
    paths = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if rel and fnmatch.fnmatch(rel, _PRODUCT_ORACLE_PATTERN):
            paths.append(_REPO_ROOT / rel)
    return paths, None

def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )

def _product_oracle_issue(path: Path, wave: int) -> str | None:
    try:
        data = json.loads(_product_oracle_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        return f"{path}: unreadable JSON ({exc})"
    if not isinstance(data, dict):
        return f"{path}: top-level JSON value is not an object"
    if data.get("artifact_kind") != "product-oracle":
        return f"{path}: artifact_kind is not product-oracle"
    if data.get("wave") != wave:
        return f"{path}: wave is not {wave}"
    arcface = data.get("arcface")
    if not isinstance(arcface, dict) or not _finite_number(arcface.get("arc_score")):
        return f"{path}: missing finite arcface.arc_score"
    lipsync = data.get("lipsync")
    if not isinstance(lipsync, dict) or not _finite_number(lipsync.get("offset_frames")):
        return f"{path}: missing finite lipsync.offset_frames"
    return None

def _product_oracle_text(path: Path) -> str:
    """Read artifact content from HEAD when the path belongs to the repo."""
    try:
        rel = path.resolve().relative_to(_REPO_ROOT.resolve())
    except (OSError, ValueError):
        return path.read_text()

    args = ["git", "show", f"HEAD:{rel.as_posix()}"]
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
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "git show failed").strip()
        raise OSError(msg)
    return proc.stdout

def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)

def _product_oracle_report(paths: list[Path], wave: int) -> dict:
    valid: list[str] = []
    invalid: list[str] = []
    for path in paths:
        issue = _product_oracle_issue(path, wave)
        if issue:
            invalid.append(issue)
        else:
            valid.append(_display_path(path))
    return {"valid": valid, "invalid": invalid}

def _has_xfail_signal(pytest_result: dict | None) -> bool:
    if not pytest_result:
        return False
    return bool(_XFAIL_SIGNAL_RE.search(
        f"{pytest_result.get('stdout', '')}\n{pytest_result.get('stderr', '')}"
    ))

def gate_report(
    inventory_path: Path,
    wave: int,
    *,
    runner: PytestRunner | None = None,
    product_oracle_paths: list[Path] | None = None,
) -> dict:
    rows = [r for r in _parse_rows(inventory_path) if r["wave"] == str(wave)]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    gate_rows = [r for r in rows if _gate_row(r)]
    selectors_by_row: dict[str, list[str]] = {}
    no_oracle_blockers: list[dict] = []
    provisional_blockers: list[dict] = []
    selectors: list[str] = []
    for row in gate_rows:
        row_selectors = _selectors_from_pin(row["xfail-pin"])
        if row_selectors:
            selectors_by_row[row["id"]] = row_selectors
            selectors.extend(row_selectors)
        else:
            no_oracle_blockers.append(_blocker(row, "no executable xfail-pin selector"))
        if row["status"] == "provisional":
            provisional_blockers.append(_blocker(row, "provisional row is not gate-clearable"))

    selectors = _dedupe(selectors)
    pytest_result = (runner or _run_pytest_selectors)(selectors) if selectors else None
    pytest_blocking = bool(
        pytest_result
        and (pytest_result["exit_code"] != 0 or _has_xfail_signal(pytest_result))
    )
    product_oracle_blockers: list[str] = []
    product_oracles = {"valid": [], "invalid": []}
    if rows and wave >= _PRODUCT_ORACLE_MIN_WAVE:
        if product_oracle_paths is None:
            product_oracle_paths, product_oracle_error = _committed_product_oracle_paths()
        else:
            product_oracle_error = None
        product_oracles = _product_oracle_report(product_oracle_paths, wave)
        if product_oracle_error:
            product_oracle_blockers.append(
                f"could not list committed {_PRODUCT_ORACLE_PATTERN} artifacts: "
                f"{product_oracle_error}"
            )
        if not product_oracles["valid"]:
            required = (
                f"Wave {wave} requires a committed {_PRODUCT_ORACLE_PATTERN} artifact "
                f"with artifact_kind=product-oracle, wave={wave}, finite "
                "arcface.arc_score, and finite lipsync.offset_frames"
            )
            if product_oracles["invalid"]:
                required += f"; invalid artifacts: {'; '.join(product_oracles['invalid'][:3])}"
            product_oracle_blockers.append(required)
    blockers = no_oracle_blockers + provisional_blockers
    return {
        "wave": wave,
        "verdict": (
            "MET"
            if not blockers and not pytest_blocking and not product_oracle_blockers
            else "UNMET"
        ),
        "counts": counts,
        "blockers": blockers,
        "product_oracle_blockers": product_oracle_blockers,
        "product_oracles": product_oracles,
        "gate_rows": gate_rows,
        "selectors": selectors,
        "selectors_by_row": selectors_by_row,
        "pytest": pytest_result,
        "pytest_blocking": pytest_blocking,
    }

def _tail(text: str, max_lines: int = 40) -> list[str]:
    lines = text.rstrip().splitlines()
    if len(lines) <= max_lines:
        return lines
    return ["..."] + lines[-max_lines:]

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("wave", type=int)
    ap.add_argument("--inventory", default=_REPO_ROOT / "docs/REMEDIATION-INVENTORY.md", type=Path)
    args = ap.parse_args(argv)
    if not args.inventory.exists():
        print(f"inventory not found: {args.inventory}", file=sys.stderr)
        return 2
    rep = gate_report(args.inventory, args.wave)
    print(f"Wave {rep['wave']} gate: {rep['verdict']}  counts={rep['counts']}")
    print(f"  gate rows: {len(rep['gate_rows'])}; executable selectors: {len(rep['selectors'])}")
    for b in rep["blockers"]:
        print(
            f"  BLOCKER [{b['severity']}/{b['status']}] {b['id']} "
            f"({b['file:line']}): {b['block_reason']}"
        )
    for blocker in rep["product_oracle_blockers"]:
        print(f"  PRODUCT ORACLE BLOCKER: {blocker}")
    for artifact in rep["product_oracles"]["valid"]:
        print(f"  PRODUCT ORACLE: {artifact}")
    if rep["pytest"]:
        print(f"  PYTEST: exit={rep['pytest']['exit_code']} command={rep['pytest']['command']}")
        output = "\n".join(
            _tail(rep["pytest"].get("stdout", ""))
            + _tail(rep["pytest"].get("stderr", ""))
        )
        if output:
            print("  PYTEST output tail:")
            for line in output.splitlines():
                print(f"    {line}")
    return 0 if rep["verdict"] == "MET" else 1

if __name__ == "__main__":
    sys.exit(main())
