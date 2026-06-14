#!/usr/bin/env python3
"""Wave-gate checker for the hardening campaign (spec §5 acceptance, §6f).

Reads docs/REMEDIATION-INVENTORY.md and reports, for a wave, whether the gate is MET:
every CRITICAL/MAJOR row in the wave is `verified` and no `provisional` row remains.
Read-only — never mutates the inventory.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

_COLS = ("id", "subsystem", "file:line", "severity", "priority", "fail-mode",
         "repro", "xfail-pin", "lane-owner", "shared-lock", "wave", "status",
         "verifier", "notes")
_BLOCK_SEV = {"CRITICAL", "MAJOR"}

def _parse_rows(inventory_path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in inventory_path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(_COLS):           # header / separator / malformed
            continue
        row = dict(zip(_COLS, cells))
        if row["id"] in ("id", "----", "") or set(row["id"]) <= {"-"}:
            continue
        rows.append(row)
    return rows

def gate_report(inventory_path: Path, wave: int) -> dict:
    rows = [r for r in _parse_rows(inventory_path) if r["wave"] == str(wave)]
    blockers = [
        r for r in rows
        if r["status"] == "provisional"
        or (r["severity"].upper() in _BLOCK_SEV and r["status"] != "verified")
    ]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "wave": wave,
        "verdict": "MET" if not blockers else "UNMET",
        "counts": counts,
        "blockers": blockers,
    }

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wave", type=int)
    ap.add_argument("--inventory", default="docs/REMEDIATION-INVENTORY.md", type=Path)
    args = ap.parse_args(argv)
    if not args.inventory.exists():
        print(f"inventory not found: {args.inventory}", file=sys.stderr)
        return 2
    rep = gate_report(args.inventory, args.wave)
    print(f"Wave {rep['wave']} gate: {rep['verdict']}  counts={rep['counts']}")
    for b in rep["blockers"]:
        print(f"  BLOCKER [{b['severity']}/{b['status']}] {b['id']} ({b['file:line']})")
    return 0 if rep["verdict"] == "MET" else 1

if __name__ == "__main__":
    sys.exit(main())
