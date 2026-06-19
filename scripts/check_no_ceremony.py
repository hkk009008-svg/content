#!/usr/bin/env python3
"""check_no_ceremony.py — forbid ceremony from the verification core.

CEREMONY = anything that produces the APPEARANCE of verification/enforcement
WITHOUT the substance: a green/PASS/verified signal that is NOT backed by
actually executing the check it claims to perform. The archetype (DECISIONS.md
ADR-027): wave_gate_check.py READS the inventory `status` string and runs zero
tests, so "GATE MET" proves only that a ceremony was logged.

This detector is the enforcement arm of ADR-028. It hard-fails (exit 1) on the
ceremony patterns it can detect with high precision, so new ceremony cannot be
introduced and the existing systemic ceremony stays RED until the routed fixes
(FIX-1 = gate executes pins; FIX-2 = CI runs --runxfail) land.

Rules:
  R1  xfail-strictness     every pytest.mark.xfail must be strict=True + reason=  (AST; prevention)
  R2  invisible-green      importorskip/skipif in a campaign *xfail*.py pin file that would
                           SKIP (dep genuinely absent) -> hard; dep present -> WARN (latent)
  R3  gate-executes-pins   scripts/wave_gate_check.py must EXECUTE the pins, not read status  [FIX-1]
  R4  ci-runs-runxfail     a CI workflow must run the pin suite with --runxfail               [FIX-2]
  R5  utv-not-a-row-status  `unable_to_verify` is a reviewer/operator VERDICT, never an inventory
                           row `status` — else it bypasses wave_gate_check blocking (ADR-027)  [ADR-032]

This script never modifies anything and never relaxes a gate; it only ADDS signal.
It is NOT itself a status-reader — it parses/executes against live source.

Usage:  .venv/bin/python scripts/check_no_ceremony.py   # exit 0 clean, 1 on any HARD violation
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def _is_xfail_decorator(node: ast.expr) -> ast.Call | ast.Attribute | None:
    """Return the decorator node if it is a pytest.mark.xfail (Call or bare Attribute)."""
    target = node.func if isinstance(node, ast.Call) else node
    # walk attribute chain, collect the trailing names
    names = []
    cur = target
    while isinstance(cur, ast.Attribute):
        names.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        names.append(cur.id)
    names = list(reversed(names))
    # match ...mark.xfail
    if len(names) >= 2 and names[-1] == "xfail" and names[-2] == "mark":
        return node
    return None


def rule_xfail_strictness() -> tuple[str, list[str]]:
    """R1 — every pytest.mark.xfail must carry strict=True and a non-empty reason."""
    violations: list[str] = []
    total = 0
    for py in sorted(TESTS.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError as exc:  # pragma: no cover - defensive
            violations.append(f"{py.relative_to(ROOT)}: unparseable ({exc})")
            continue
        for n in ast.walk(tree):
            decos = getattr(n, "decorator_list", None)
            if not decos:
                continue
            for d in decos:
                xf = _is_xfail_decorator(d)
                if xf is None:
                    continue
                total += 1
                rel = f"{py.relative_to(ROOT)}:{d.lineno}"
                if isinstance(xf, ast.Attribute):
                    violations.append(f"{rel}: bare @pytest.mark.xfail (no strict=, no reason=)")
                    continue
                kw = {k.arg: k.value for k in xf.keywords if k.arg}
                strict = kw.get("strict")
                if not (isinstance(strict, ast.Constant) and strict.value is True):
                    violations.append(f"{rel}: xfail without strict=True (soft xfail hides a real failure)")
                reason = kw.get("reason")
                ok_reason = reason is not None and not (
                    isinstance(reason, ast.Constant) and not str(reason.value).strip()
                )
                if not ok_reason:
                    violations.append(f"{rel}: xfail without a non-empty reason=")
    status = "PASS" if not violations else "FAIL"
    summary = f"{total} xfail markers; all strict=True+reason" if not violations else f"{len(violations)} violation(s) of {total} markers"
    return status, [summary] + violations


def rule_invisible_green() -> tuple[str, list[str], list[str]]:
    """R2 — importorskip/skipif inside campaign *xfail*.py pin files.

    HARD only when the dependency is genuinely absent (the test would silently SKIP =
    invisible green). If the dep is importable, downgrade to WARN (latent risk).
    """
    hard: list[str] = []
    warn: list[str] = []
    for py in sorted(TESTS.glob("**/*xfail*.py")):
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:  # pragma: no cover
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            name = None
            if isinstance(f, ast.Attribute):
                name = f.attr
            if name not in ("importorskip", "skip", "skipif"):
                continue
            rel = f"{py.relative_to(ROOT)}:{n.lineno}"
            if name == "importorskip" and n.args and isinstance(n.args[0], ast.Constant):
                mod = str(n.args[0].value)
                present = importlib.util.find_spec(mod) is not None
                (warn if present else hard).append(
                    f"{rel}: importorskip({mod!r}) — dep {'present (latent invisible-green risk)' if present else 'ABSENT -> test SKIPS silently = ceremony'}"
                )
            else:
                warn.append(f"{rel}: {name}() in a pin file — confirm it cannot hide the pinned defect")
    status = "FAIL" if hard else ("WARN" if warn else "PASS")
    return status, hard, warn


def rule_gate_executes() -> tuple[str, list[str]]:
    """R3 — wave_gate_check.py must EXECUTE the pins, not merely read the status column."""
    gate = ROOT / "scripts" / "wave_gate_check.py"
    if not gate.exists():
        return "PASS", ["scripts/wave_gate_check.py absent"]
    src = gate.read_text()
    markers = ("--runxfail", "subprocess", "pytest.main", "runpy", "import_module")
    if any(m in src for m in markers):
        return "PASS", ["wave_gate_check.py executes the pins"]
    return "FAIL", [
        "scripts/wave_gate_check.py reads the inventory `status` string and executes ZERO tests "
        "(ADR-027). 'GATE MET' is not a correctness claim. [FIX-1: rewrite to run the pins via --runxfail]"
    ]


def rule_ci_runs_runxfail() -> tuple[str, list[str]]:
    """R4 — a CI workflow must run the pin suite with --runxfail (catches XPASS / landed-fix regressions)."""
    wf_dir = ROOT / ".github" / "workflows"
    yamls = list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml")) if wf_dir.exists() else []
    if any("--runxfail" in y.read_text() for y in yamls):
        return "PASS", ["a CI workflow runs --runxfail"]
    return "FAIL", [
        ".github/workflows/* never runs pytest with --runxfail, so the 70+ strict-xfail pins are "
        "never executed as a gate — they are CI-ceremony. [FIX-2: add a --runxfail pin-execution step]"
    ]


def _inventory_data_rows(text: str) -> list[list[str]]:
    """Stripped pipe-delimited cells of each DATA row in the inventory table.

    Skips the `| id | subsystem | ... |` header, the `|---|` separator, and any
    non-table line. Robust to the surrounding markdown.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if set("".join(cells)) <= set("-: "):  # |---|:--| separator row
            continue
        lowered = [c.lower() for c in cells]
        if lowered[0] == "id" and "subsystem" in lowered:  # header
            continue
        rows.append(cells)
    return rows


def _utv_status_violations(text: str) -> list[str]:
    """Rows where any cell is EXACTLY `unable_to_verify` (case-insensitive).

    UTV is a verdict token; legitimately it can only ever be a standalone status
    cell, never embedded in prose — so an exact full-cell match is high-precision
    and immune to column miscounting from stray pipes in free-text cells.
    """
    bad: list[str] = []
    for cells in _inventory_data_rows(text):
        rid = cells[0] if cells else "<?>"
        for i, c in enumerate(cells):
            if c.lower() == "unable_to_verify":
                bad.append(
                    f"row {rid!r}: cell #{i} == 'unable_to_verify' — UTV is a reviewer/operator "
                    "verdict, never a row status (it would bypass wave_gate_check blocking)"
                )
    return bad


def rule_utv_not_a_row_status() -> tuple[str, list[str]]:
    """R5 — `unable_to_verify` must never be an inventory row status (ADR-027 / ADR-032).

    wave_gate_check.py tallies any status string but blocks only on severity/provisional,
    so a UTV row status would be silently NON-blocking — green-washing an unverified row.
    UTV is the reviewer/operator could-not-conclude VERDICT; the row stays in its prior
    state (typically `open`) and the receiving seat RE-DISPATCHES in a fixed env.
    """
    inv = ROOT / "docs" / "REMEDIATION-INVENTORY.md"
    if not inv.exists():
        return "PASS", ["docs/REMEDIATION-INVENTORY.md absent"]
    violations = _utv_status_violations(inv.read_text())
    if violations:
        return "FAIL", violations
    return "PASS", ["no inventory row uses unable_to_verify as a status (it is a verdict only)"]


def main() -> int:
    print("CEREMONY CHECK — forbid appearance-of-verification-without-substance (ADR-027 / ADR-028)\n")
    hard_fail = False

    r1_status, r1 = rule_xfail_strictness()
    print(f"R1 xfail-strictness ....... {r1_status}  {r1[0]}")
    for v in r1[1:]:
        print(f"     - {v}")
    hard_fail |= r1_status == "FAIL"

    r2_status, r2_hard, r2_warn = rule_invisible_green()
    print(f"R2 invisible-green ........ {r2_status}")
    for v in r2_hard:
        print(f"     ! {v}")
    for v in r2_warn:
        print(f"     ~ {v}")
    hard_fail |= r2_status == "FAIL"

    r3_status, r3 = rule_gate_executes()
    print(f"R3 gate-executes-pins ..... {r3_status}  {r3[0]}")
    hard_fail |= r3_status == "FAIL"

    r4_status, r4 = rule_ci_runs_runxfail()
    print(f"R4 ci-runs-runxfail ....... {r4_status}  {r4[0]}")
    hard_fail |= r4_status == "FAIL"

    r5_status, r5 = rule_utv_not_a_row_status()
    print(f"R5 utv-not-a-row-status ... {r5_status}  {r5[0]}")
    for v in r5[1:]:
        print(f"     ! {v}")
    hard_fail |= r5_status == "FAIL"

    print()
    if hard_fail:
        print("RESULT: HARD ceremony violation(s) present — the verification core is not fully self-executing.")
        print("        R3/R4 are the known systemic ceremony tracked by ADR-027 FIX-1/FIX-2 (routed to a director).")
        return 1
    print("RESULT: no ceremony detected — every relied-on green is backed by execution.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
