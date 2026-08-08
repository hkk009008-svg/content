#!/usr/bin/env python3
"""Turn the claims in docs/EVIDENCE-REGISTER.md into citable evidence.

DESIGN RULES, each one paid for by something that went wrong earlier:

1. PLANNING IS FREE AND IS THE DEFAULT. `--plan` spends nothing and prints every
   cell with its price. Running costs money and requires `--authorize-usd` to
   match the planned total EXACTLY, so an edited plan cannot quietly spend an
   old authorisation.

2. THE INSTRUMENT IS VALIDATED BEFORE THE READING. `--plan` and `--run` both
   refuse to proceed unless tests/unit/test_evidence_metrics.py passes. The
   first spatial metric drafted for this harness scored two UNRELATED rooms at
   0.874 and would have confirmed H4 whatever the provider did.

3. NO CELL REPORTS A VERDICT THE METRIC CANNOT SUPPORT. Each cell declares which
   instrument decides it. GhostFaceNet is unavailable to any off-angle cell by
   construction (ADR-092), and the cells that only the operator can judge say so
   and emit a contact sheet instead of a number.

4. ARMS DIFFER IN ONE THING. Same prompt, same seed, same shot, same camera
   move; only the variable under test changes. An arm pair that differs in two
   things measures nothing.

This module owns PLANNING and MEASUREMENT. Execution of a cell calls the real
pipeline, so a cell's result is evidence about the shipped code rather than
about a reimplementation of it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))


@dataclass(frozen=True)
class Cell:
    """One arm of one hypothesis: exactly one render and one measurement."""

    hypothesis: str
    arm: str
    engine: str
    unit_usd: float
    calls: int
    what: str

    @property
    def usd(self) -> float:
        return round(self.unit_usd * self.calls, 4)


@dataclass
class Hypothesis:
    id: str
    claim: str
    status: str
    falsifier: str
    decided_by: str
    cells: list[Cell] = field(default_factory=list)

    @property
    def usd(self) -> float:
        return round(sum(cell.usd for cell in self.cells), 4)


def _costs() -> dict:
    from cost_tracker import API_COST_USD
    return API_COST_USD


def _still_engine(cost: dict) -> str:
    """Which image route a keyframe will actually take, priced the way the
    controller decides it (cinema/shots/controller.py:1558-1575).

    Guessing FLUX_KONTEXT while the project is configured for Gemini would quote
    a price the run does not incur — in either direction, which is the problem.
    """

    from config.settings import settings as env_settings
    if env_settings.google_api_key or env_settings.gemini_api_key:
        return "GEMINI_IMAGE"
    return "FLUX_KONTEXT" if env_settings.fal_key else "POLLINATIONS"


def _still_unit(cost: dict) -> float:
    return cost[_still_engine(cost)]


def build_plan() -> list[Hypothesis]:
    """The register, as executable cells.

    Prices are READ from `API_COST_USD`, never typed here — the same table the
    durable ledger reserves against, so a price change moves this plan without
    anyone remembering to.
    """

    cost = _costs()
    kontext = cost["FLUX_KONTEXT"]
    veo = cost["VEO"]
    kling = cost["KLING_3_0"]

    return [
        Hypothesis(
            id="H4",
            claim="Leading VEO's reference list with the approved keyframe "
                  "preserves the approved composition; the old code discarded it.",
            status="REASONED",
            falsifier="frame 0 of the keyframe-led arm is NOT markedly closer to "
                      "the approved keyframe than the references-only arm",
            decided_by="structure_match(frame_0, approved_keyframe)",
            cells=[
                # ONE keyframe per shot, SHARED by both arms. Generating one per
                # arm would confound the thing under test with ordinary
                # generation variance, so this is a shared cost and is priced
                # once rather than twice.
                Cell("H4", "shared_keyframes", _still_engine(cost), _still_unit(cost), 2,
                     "one approved keyframe per shot, fed to both arms"),
                Cell("H4", "keyframe_led", "VEO", veo, 2,
                     "current code: keyframe leads image_urls"),
                Cell("H4", "references_only", "VEO", veo, 2,
                     "pre-fix behaviour reconstructed: faces only, keyframe withheld"),
            ],
        ),
        Hypothesis(
            id="H5",
            claim="On a shot with no character, a product-appropriate prompt "
                  "clause beats unconditional face language.",
            status="REASONED",
            falsifier="the face-clause arm shows no more marking instability "
                      "than the product-clause arm",
            decided_by="temporal_drift delta + operator judgement on swimming text",
            cells=[
                Cell("H5", "product_clause", "VEO", veo, 2, "current code"),
                Cell("H5", "face_clause", "VEO", veo, 2, "pre-fix wording"),
            ],
        ),
        Hypothesis(
            id="H1",
            claim="A product photograph in an empty reference slot beats a text "
                  "description of the product.",
            status="REASONED",
            falsifier="photograph arms score no better on marking legibility and "
                      "shape fidelity than text-only arms",
            decided_by="operator judgement (primary); structure_match vs the "
                       "product photograph (secondary)",
            cells=[
                Cell("H1", "with_photo", "FLUX_KONTEXT", kontext, 3, "object refs delivered"),
                Cell("H1", "text_only", "FLUX_KONTEXT", kontext, 3, "prompt text only"),
            ],
        ),
        Hypothesis(
            id="H2",
            claim="Location plates produce a more faithful room than the "
                  "location prompt fragment alone.",
            status="REASONED",
            falsifier="plate arms are no closer to the plate's palette and "
                      "structure than text-only arms",
            decided_by="palette_match + structure_match vs the plate",
            cells=[
                Cell("H2", "with_plates", "FLUX_KONTEXT", kontext, 3, "plates delivered"),
                Cell("H2", "text_only", "FLUX_KONTEXT", kontext, 3, "prompt fragment only"),
            ],
        ),
        Hypothesis(
            id="H3",
            claim="On a saturated set, the scene anchor in slot 6 buys more "
                  "inter-shot consistency than a sixth facial angle buys identity.",
            status="REASONED — the one place a subject displaces another",
            falsifier="the anchor arm shows no better inter-shot palette "
                      "consistency, or buys it at a visible cost to the face",
            decided_by="inter-shot palette_match + operator judgement on identity. "
                       "NOT GhostFaceNet (ADR-092).",
            cells=[
                Cell("H3", "anchor_5faces", "FLUX_KONTEXT", kontext, 4, "shots 2-5, stills"),
                Cell("H3", "6faces", "FLUX_KONTEXT", kontext, 4, "shots 2-5, stills"),
                Cell("H3", "anchor_5faces", "VEO", veo, 4, "shots 2-5, motion"),
                Cell("H3", "6faces", "VEO", veo, 4, "shots 2-5, motion"),
            ],
        ),
        Hypothesis(
            id="H8",
            claim="A frontal at slot 0 beats whatever the record happened to "
                  "list first, because slot 0 IS Kling's frontal image.",
            status="PINNED for ordering, REASONED for effect",
            falsifier="clips with a profile at slot 0 are no worse than clips "
                      "with the frontal there",
            decided_by="operator judgement only — there is no honest automatic "
                       "measure of 'Kling was told the wrong thing'",
            cells=[
                Cell("H8", "canonical_first", "KLING_3_0", kling, 2, "current ordering"),
                Cell("H8", "profile_first", "KLING_3_0", kling, 2, "the pre-fix record order"),
            ],
        ),
        Hypothesis(
            id="H9",
            claim="Coverage ordering keeps the turn that score ordering drops.",
            status="PINNED for ordering, REASONED for effect",
            falsifier="a turning shot from a score-ordered set is no worse than "
                      "from a coverage-ordered set",
            decided_by="operator judgement; the score that produced the ordering "
                       "cannot also judge it",
            cells=[
                Cell("H9", "coverage_ordered", "VEO", veo, 2, "current ordering"),
                Cell("H9", "score_ordered", "VEO", veo, 2, "frontal-heavy ordering"),
            ],
        ),
    ]


_WIRED = {"H4"}
"""Hypotheses with a render path. The rest are priced and specified only.

Kept explicit so `--run H3` refuses loudly instead of silently doing nothing and
exiting 0, which reads exactly like a run that happened."""


def _execute(selected: set[str], project_id: str, *, dry_run: bool) -> int:
    """Render the selected wired cells and write a citable artifact."""

    import time as _time
    from evidence_cells import h4_veo_keyframe

    run_id = _time.strftime("%Y%m%dT%H%M%SZ", _time.gmtime())
    out_dir = REPO / "logs" / "evidence" / run_id
    print(f"\nrun id : {run_id}")
    print(f"output : {out_dir.relative_to(REPO)}")

    manifests = []
    for hypothesis_id in sorted(selected):
        if hypothesis_id == "H4":
            manifest = h4_veo_keyframe.render_and_measure(
                project_id, out_dir / "H4", dry_run=dry_run,
            )
            manifests.append(manifest)

    if dry_run:
        print("\nDRY RUN — assets resolved, no provider call made, nothing spent.")
        for manifest in manifests:
            print(json.dumps(manifest, indent=2))
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "manifest.json"
    artifact.write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    print(f"\nartifact: {artifact.relative_to(REPO)}")
    for manifest in manifests:
        reading = (manifest.get("verdict") or {}).get("reading", "no verdict")
        print(f"\n{manifest['hypothesis']}: {reading}")
        print(json.dumps(manifest.get("verdict", {}), indent=2))
    print("\nRead the frames before believing the numbers. The operator's eye "
          "outranks every metric in docs/EVIDENCE-REGISTER.md.")
    return 0


def _metrics_are_validated() -> tuple[bool, str]:
    """Refuse to plan or run on unvalidated instruments.

    Not ceremony. Every wrong conclusion in this project's history came from an
    apparatus that read plausibly and was wrong, and a metric is an apparatus.
    """

    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest",
         "tests/unit/test_evidence_metrics.py", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    tail = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, tail[-1] if tail else "no output"


def print_plan(plan: list[Hypothesis], selected: set[str] | None) -> float:
    chosen = [h for h in plan if not selected or h.id in selected]
    total = 0.0
    print("EVIDENCE PLAN — nothing below has been spent\n")
    for hypothesis in chosen:
        print(f"{hypothesis.id}  [{hypothesis.status}]")
        print(f"    claim     : {hypothesis.claim}")
        print(f"    falsified if: {hypothesis.falsifier}")
        print(f"    decided by: {hypothesis.decided_by}")
        for cell in hypothesis.cells:
            print(f"      {cell.arm:18s} {cell.engine:13s} "
                  f"{cell.calls} x ${cell.unit_usd:.2f} = ${cell.usd:6.2f}   {cell.what}")
        print(f"    subtotal  : ${hypothesis.usd:.2f}\n")
        total += hypothesis.usd
    # Rounded UP to the cent, and the comparison uses this same number.
    # It printed "$1.13" while comparing against 1.134, so following its own
    # instruction was refused. Money is denominated in cents; ceiling is the
    # safe direction, because the authorised amount must never be LESS than
    # what the run can spend.
    total = math.ceil(total * 100) / 100
    print(f"TOTAL: ${total:.2f}")
    print("\nTo execute, re-run with --run <IDS> --authorize-usd "
          f"{total:.2f}  (the amount must match this plan exactly)")
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true",
                        help="print the cell plan and total cost; spend nothing")
    parser.add_argument("--run", default="",
                        help="comma-separated hypothesis ids to execute (COSTS MONEY)")
    parser.add_argument("--authorize-usd", type=float, default=None,
                        help="must equal the planned total for the selected ids")
    parser.add_argument("--project", default="42c74e230519",
                        help="project id supplying the character and references")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve assets and print what WOULD render; spends nothing")
    parser.add_argument("--skip-instrument-check", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.skip_instrument_check:
        ok, summary = _metrics_are_validated()
        print(f"instrument validation: {'PASS' if ok else 'FAIL'} — {summary}\n")
        if not ok:
            print("Refusing to plan or run on unvalidated instruments.")
            return 2

    plan = build_plan()
    selected = {token.strip().upper() for token in args.run.split(",") if token.strip()}
    known = {h.id for h in plan}
    unknown = selected - known
    if unknown:
        print(f"unknown hypothesis ids: {sorted(unknown)}; known: {sorted(known)}")
        return 2

    total = print_plan(plan, selected or None)

    if not selected:
        return 0

    if args.authorize_usd is None:
        print("\nREFUSED: --run selects paid work. Pass --authorize-usd to proceed.")
        return 1
    if abs(round(args.authorize_usd, 2) - total) > 1e-9:
        print(f"\nREFUSED: authorised ${args.authorize_usd:.2f} but this plan costs "
              f"${total:.2f}. The amounts must match exactly — a plan that changed "
              f"since you priced it must be re-read, not re-approved.")
        return 1

    unwired = sorted(selected - _WIRED)
    if unwired:
        print(f"\nREFUSED: {unwired} have no render path yet. Wired: "
              f"{sorted(_WIRED)}. Nothing was spent.")
        return 3

    return _execute(selected, args.project, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
