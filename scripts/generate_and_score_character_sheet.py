#!/usr/bin/env python3
"""Generate a character's turnaround sheet and score every panel for identity.

WHY
---
`domain.character_manager._generate_multi_angle_refs` has always been able to
turn one uploaded photo into a five-panel sheet — 45-degree, profile, back,
smile, outdoor-lighting — via FLUX Kontext. It has never run for this project's
subject: two guards skip it, and the FAL-unavailable branch skips SILENTLY,
returning only the canonical. So the character shows two angles that came from
the Identity Lab consent set, and the sheet feature looks absent rather than
un-run.

This matters now because the 2026 survey found that video models COPY identity
rather than invent it, and every shipping reference-to-video path wants a SET:
Gemini 3 Pro Image up to 5 character images, Veo 3.1 three, Seedance up to 30.
The sheet — not a single hero keyframe — is the identity deliverable.

But the sheet's own fidelity has never been measured. Kontext is asked to
"PRESERVE IDENTITY" and may drift the face while claiming not to. A sheet that
looks plausible and scores 0.5 would poison every downstream video reference,
so it is scored here against the canonical before anything is asked to trust it.

READ THE SCORES WITH TWO CAVEATS
--------------------------------
* `angle_back` shows the back of a head. There is no face to score, so expect
  no detection — that is correct behaviour, not a failure.
* `angle_profile` is a 90-degree view. Face embedders lose accuracy on profiles
  and the published GhostFaceNet benchmark SKIPS undetectable turned-away
  frames entirely. A low profile score may be the scorer, not the panel — so
  the detection outcome is reported alongside the number.

THIS SPENDS REAL MONEY: 5 panels x $0.08 = $0.40 on fal (FLUX Kontext Max
Multi). Every panel is reserved through the durable paid-attempt ledger first,
so an interrupted run resumes its request IDs instead of paying twice.

    env -u GIT_INDEX_FILE .venv/bin/python scripts/generate_and_score_character_sheet.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import web_server  # noqa: E402,F401  (TF before PyArrow)

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import domain.character_manager as cm  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402
from identity.types import get_threshold_for_shot  # noqa: E402


DEFAULT_PROJECT = "42c74e230519"
DEFAULT_CHARACTER = "hkkperson"

# Which shot type each panel most resembles, so the gate matches the panel.
# A back-of-head panel has no meaningful gate; it is reported, never judged.
PANEL_SHOT_TYPE = {
    "angle_45": "portrait",
    "angle_profile": "portrait",
    "angle_back": None,
    "expression_smile": "portrait",
    "lighting_outdoor": "portrait",
}


def _score(image: Path, reference: Path, character_id: str, shot_type: str):
    from identity import validator as validator_module

    gate = get_threshold_for_shot(shot_type)
    if not validator_module.DEEPFACE_AVAILABLE:
        return None, "unavailable", gate
    validator = validator_module.IdentityValidator(vision_fallback=None)
    result = validator.validate_image(
        str(image), str(reference), character_id=character_id,
        shot_type=shot_type, threshold=gate,
    )
    if result.skipped or result.overall_score is None:
        return None, "no_face_or_skipped", gate
    return float(result.overall_score), "passed" if result.passed else "failed", gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--character", default=DEFAULT_CHARACTER)
    parser.add_argument("--out", default="logs/character-sheet")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the plan and the exact cost, spend nothing",
    )
    args = parser.parse_args()

    project_path = Path("domain/projects") / args.project / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    character = cm.get_character(project, args.character)
    if not character:
        print(f"character not found: {args.character}")
        return 2
    canonical = Path(
        cm._resolve_stored_media_path(project, character.get("canonical_reference", ""))
    )
    char_dir = canonical.parent

    total = cm._FLUX_KONTEXT_COST_USD * len(cm._ANGLE_CONFIGS)
    print(f"subject   : {args.character}")
    print(f"canonical : {canonical.name}")
    print(f"engine    : {cm._FLUX_KONTEXT_APPLICATION}")
    print(f"panels    : {', '.join(c['name'] for c in cm._ANGLE_CONFIGS)}")
    print(f"cost      : {len(cm._ANGLE_CONFIGS)} x ${cm._FLUX_KONTEXT_COST_USD:.2f}"
          f" = ${total:.2f}")
    print(f"writes to : {char_dir}/<panel>.jpg\n")
    if args.dry_run:
        print("dry run — nothing spent, nothing written")
        return 0

    if not cm.FAL_AVAILABLE or not getattr(cm.settings, "fal_key", ""):
        print("FAL unavailable or no key — the generator would silently skip. Stopping.")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker(db_path=str(out_dir / "sheet.db"), budget_usd=2.0)
    evidence: list[dict] = []
    started = time.monotonic()
    try:
        paths = cm._generate_multi_angle_refs(
            str(canonical),
            str(char_dir),
            character.get("description", ""),
            cost_tracker=tracker,
            video_id=f"sheet-{args.character}",
            character_id=args.character,
            artifact_evidence_out=evidence,
        )
    finally:
        tracker.close()
    elapsed = time.monotonic() - started
    print(f"\ngenerated {len(paths) - 1} panels in {elapsed:.1f}s"
          f" (index 0 is the canonical itself)\n")

    rows = []
    for path in paths[1:]:
        panel = Path(path)
        name = panel.stem
        shot_type = PANEL_SHOT_TYPE.get(name)
        if shot_type is None:
            print(f"{name:<20} no face by design — not scored")
            rows.append({"panel": name, "path": panel.name, "score": None,
                         "verdict": "not_scored_by_design"})
            continue
        score, verdict, gate = _score(panel, canonical, args.character, shot_type)
        shown = "—" if score is None else f"{score:.3f}"
        print(f"{name:<20} score={shown}  gate={gate:.2f}  {verdict}")
        rows.append({"panel": name, "path": panel.name, "shot_type": shot_type,
                     "gate": gate, "score": score, "verdict": verdict})

    (out_dir / "sheet.json").write_text(
        json.dumps({"character": args.character, "canonical": canonical.name,
                    "engine": cm._FLUX_KONTEXT_APPLICATION,
                    "spend_usd": round(total, 2), "panels": rows,
                    "evidence": evidence}, indent=2) + "\n", "utf-8")

    scored = [r["score"] for r in rows if r.get("score") is not None]
    print(f"\nspent ~${total:.2f}   panels written into {char_dir}")
    if scored:
        print(f"scored panels: {len(scored)}   "
              f"min {min(scored):.3f}   mean {sum(scored)/len(scored):.3f}   "
              f"max {max(scored):.3f}")
    print(
        "\nA panel that scores well is a usable video reference. A panel that\n"
        "scores badly would poison every downstream reference-to-video call, so\n"
        "read the images too — Kontext can drift a face while the prompt says\n"
        "PRESERVE IDENTITY."
    )
    print(
        "NOTE: the character record's multi_angle_refs is NOT updated by this\n"
        "script. Wire the panels in deliberately once you have judged them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
