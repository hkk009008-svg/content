#!/usr/bin/env python3
"""Put a character's whole reference set into the field the video models read.

WHY
---
`multi_angle_refs` is what reaches the video providers. controller.py forwards
`multi_angle_refs=cc.get("multi_angle_refs", [])` and phase_c_ffmpeg slices it
`[:4]` (Veo) or `[:8]` (reference-to-video), and those images ARE the identity
the model copies — LTX states it "does not reproduce
identities that are absent from the supplied sheet".

For this project's character the field held TWO paths while TEN usable images
sat on disk, so the slices never even fired. The bottleneck was the record, not
the caps. And there is no way to fix it through the UI: the character PUT route
(web_server.py:3226) writes only name, description, voice_id, physical_traits —
`multi_angle_refs` is written at creation and never again.

CORRECTION (made after an independent trace disagreed with this file)
--------------------------------------------------------------------
An earlier version of this docstring claimed the provider paths "prepend the
canonical". That is TRUE of phase_c_assembly.py:915
(`[character_image, *multi_angle_refs]`) and FALSE of the video path:
phase_c_ffmpeg.py:2122 iterates `multi_angle_refs[:4]` with no canonical, and
phase_c_ffmpeg.py:2247 uploads `valid_refs[0]` as the KLING FRONTAL IMAGE.

So slot 0 of this list is labelled "frontal" to Kling. A coverage-first ordering
that opens with a profile therefore tells Kling a profile is the frontal view.
The canonical is now slot 0 explicitly. phase_c_assembly will see it twice and
waste one slot of six; a correctly-labelled frontal is worth more than that
slot. The durable fix is to prepend at domain/continuity_engine.py:463 so every
consumer agrees, which is a code change and not done here.

ORDER IS THE DESIGN
-------------------
Providers truncate. Veo takes 3 references, Seedance up to 30, and this pipeline
slices at 4 and 8. So the ORDER decides what survives, and the list is therefore
ordered for COVERAGE rather than for score: the most angularly distinct images
first after the canonical, so even a 3-slot provider receives a frontal, a
profile, and a three-quarter instead of three near-identical frontals.

This is why selection cannot be score-driven (ADR-092). Ranking by identity
score returns only frontal images — the subject's own real profile photograph
scores 0.556 and "fails" — and would discard exactly the views a turning
character needs.

    env -u GIT_INDEX_FILE .venv/bin/python scripts/wire_character_reference_set.py --dry-run
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import argparse  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from domain.models import Project  # noqa: E402
from domain.project_manager import mutate_project  # noqa: E402


DEFAULT_PROJECT = "42c74e230519"
DEFAULT_CHARACTER = "hkkperson"

# Ordered for COVERAGE after the canonical: most angularly distinct first, so
# truncation at 3, 4 or 8 still yields a varied set rather than three frontals.
ORDERED_SET = [
    ("characters/hkkperson_canonical_front_closeup.jpg",
     "The canonical. Slot 0 because phase_c_ffmpeg.py:2247 uploads valid_refs[0] "
     "as Kling's FRONTAL image and nothing prepends it there"),
    ("characters/hkkperson_angle_left_profile.jpg",
     "REAL profile photograph — maximum angular distance from the canonical"),
    ("characters/hkkperson_angle_right_threequarter.jpg",
     "REAL three-quarter, opposite side — covers the other turn direction"),
    ("characters/hkkperson_reference_front_wide.jpg",
     "REAL wide framing — the face at a different scale. Placed before any "
     "generated panel so the four REAL photographs occupy slots 0-3: "
     "get_identity_reference_paths stops at 4, and putting a generated image "
     "there silently changed which set the Identity Lab would consent to"),
    ("characters/lighting_outdoor.jpg",
     "Highest identity of any image available (0.922); adds daylight. First "
     "GENERATED panel — provenance-ordered: photographs, then derived"),
    ("characters/angle_45.jpg",
     "Generated 45-degree turn; fills the gap between frontal and three-quarter"),
    ("characters/threequarter_smile.jpg",
     "Angle AND expression together — a combination no other reference has"),
    ("characters/profile_outdoor.jpg",
     "Second profile, different light. Generated FROM the real profile and "
     "confirmed by the subject as him"),
    ("characters/expression_smile.jpg",
     "Frontal expression variation"),
    ("characters/angle_back.jpg",
     "Back of head — no face to score, but hair and wardrobe continuity for video"),
]

# Never wire this in. Generated from the FRONTAL photo, so the model invented a
# side of a head it had never seen; the subject confirmed it is NOT him. It
# scored 0.570, ABOVE both his real profile (0.556) and the panel that is him
# (0.539) — the rank inversion that ADR-092 records. Quarantined on disk.
EXCLUDED = {"characters/angle_profile.jpg"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--character", default=DEFAULT_CHARACTER)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path("domain/projects") / args.project
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    char = next((c for c in project["characters"] if c["id"] == args.character), None)
    if not char:
        print(f"character not found: {args.character}")
        return 2

    missing = [rel for rel, _ in ORDERED_SET if not (root / rel).is_file()]
    if missing:
        print("refusing to wire a set with missing files:")
        for rel in missing:
            print(f"   {rel}")
        return 2
    for rel in EXCLUDED:
        if (root / rel).is_file():
            print(f"refusing: quarantined file is back on disk: {rel}")
            return 2

    before = list(char.get("multi_angle_refs") or [])
    after = [rel for rel, _ in ORDERED_SET]

    print(f"character : {args.character}")
    print(f"canonical : {char.get('canonical_reference')}  (slot 0 of the list below)")
    print(f"\nBEFORE  multi_angle_refs = {len(before)} reference(s)")
    for rel in before:
        print(f"   {rel}")
    print(f"\nAFTER   multi_angle_refs = {len(after)} references, coverage-ordered")
    for i, (rel, why) in enumerate(ORDERED_SET, 1):
        print(f"  {i:>2}. {Path(rel).name}")
        print(f"      {why}")

    print("\nwhat each consumer would receive from this list (truncated):")
    for label, cap in (("phase_c_ffmpeg [:4]", 4), ("Kling frontal+[1:4]", 4),
                       ("reference-to-video [:8]", 8), ("full list", len(after))):
        names = [Path(r).stem for r, _ in ORDERED_SET][:cap]
        print(f"   {label:<26} {len(names):>2}: {', '.join(names)}")

    if args.dry_run:
        print("\ndry run — nothing written")
        return 0

    def _mutate(latest: dict):
        target = next(
            (c for c in latest["characters"] if c["id"] == args.character), None
        )
        if target is None:
            raise ValueError("character vanished during mutation")
        target["multi_angle_refs"] = after
        return target

    mutate_project(args.project, _mutate, timeout=10)

    reloaded = json.loads((root / "project.json").read_text(encoding="utf-8"))
    Project.model_validate(reloaded)
    saved = next(c for c in reloaded["characters"] if c["id"] == args.character)
    written = list(saved.get("multi_angle_refs") or [])
    print(f"\nwritten and re-validated: {len(written)} references")
    if written != after:
        print("MISMATCH — the persisted list is not what was intended")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
