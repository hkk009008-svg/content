#!/usr/bin/env python3
"""Re-test the ADR-089 one-reference default under prompts that do real work.

WHY THIS EXISTS
---------------
ADR-089 defaulted the local FLUX.2 graph to one reference per character, on the
Identity Lab's measurement: 1 ref 0.791 PASS, 2 refs 0.766 PASS, 4 refs 0.499
FAIL. That measurement used a single prompt, and it was a generous one --
BENCHMARK_PROMPT literally contains "the same person", "preserve exact facial
identity", and "realistic skin texture". A render that holds up under those
words has not been asked to do much.

The open question is whether one reference still wins when the prompt spends
its weight on a scene instead of on identity: a wide shot where the face is
small, a profile where the dropped angle references might have been earning
something, low light, motion. This harness renders a battery of director-style
prompts at BOTH the new default (1 reference) and the old behaviour (4), scores
each with the same validator the lab used, and writes them side by side.

It is deliberately a probe, not a gate. Six prompts times two arms is a small
sample on one subject; treat a reversal on one cell as a lead, not a verdict.
Read the images -- a score above the gate on a face that looks wrong is still a
failure, and the numbers here cannot see that.

REQUIREMENTS
------------
* The Windows GPU worker up and its gateway reachable (the SSH tunnel on
  127.0.0.1:18189). Local GPU work costs no provider money.
* Run from the repository root with the project venv:

    env -u GIT_INDEX_FILE .venv/bin/python scripts/adr089_prompt_battery.py

WHAT IT DOES NOT COVER
----------------------
* The LLM shot decomposition. `decompose_scene` requires OPENAI_API_KEY and is
  real paid spend, so the prompts below are hand-authored in the shape a
  director pass produces. This tests the RENDER under realistic prompts, not
  the prompt writer.
* Multi-character allocation, which needs a second consented subject.
* The full `generate_keyframe_take` plumbing (take records, artifact versions).
  This drives the same allocator and the same pinned builder those use.
"""

from __future__ import annotations

import os
import sys

# Bootstrap sys.path so the repo root imports regardless of CWD (matches
# scripts/ci_smoke.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# TensorFlow must be imported before pandas pulls in PyArrow, or the Abseil
# symbols collide. web_server does this first; mirror it here.
import web_server  # noqa: E402,F401  (import for side effect: TF before PyArrow)

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

from cinema.shots.strategy import (  # noqa: E402
    CharIdentitySpec,
    allocate_flux2_references,
)
from cost_tracker import CostTracker  # noqa: E402
from domain.character_manager import (  # noqa: E402
    _resolve_stored_media_path,
    get_character,
)
from identity.protocols import BENCHMARK_PROMPT  # noqa: E402
from performance.flux2_klein import run_flux2_klein_image_job  # noqa: E402


DEFAULT_PROJECT = "42c74e230519"
DEFAULT_CHARACTER = "hkkperson"
IDENTITY_GATE = 0.70


@dataclass(frozen=True)
class Case:
    key: str
    prompt: str
    why: str


# Ordered easiest to hardest. The first is the lab's own prompt, kept as an
# anchor: if it does not reproduce ~0.791 the run is not comparable to anything
# and the rest of the numbers should be discarded.
CASES = (
    Case(
        "anchor",
        BENCHMARK_PROMPT,
        "The lab's own prompt. Anchors this run against the 0.791 measurement.",
    ),
    Case(
        "neutral_portrait",
        "Portrait photograph of a person, studio lighting, neutral gray "
        "background, looking directly at the camera.",
        "Same framing as the anchor but with every identity-preserving phrase "
        "removed. Isolates how much of the anchor's score came from the words.",
    ),
    Case(
        "medium_action",
        "Medium shot of a man in a charcoal wool coat stepping out of a "
        "bookshop doorway onto a wet city street, late afternoon, overcast "
        "light, shallow depth of field.",
        "The prompt now spends its weight on wardrobe, setting, and light. "
        "This is the ordinary case a director pass produces.",
    ),
    Case(
        "wide_small_face",
        "Wide establishing shot of a lone figure crossing an empty concrete "
        "plaza at dusk, city skyline behind, cool blue hour light, figure "
        "small in frame.",
        "The face occupies few pixels. The hardest case for reference "
        "conditioning, and where a thin identity signal should fail first.",
    ),
    Case(
        "profile_angled",
        "Close profile shot of a man looking off to his left, side lighting "
        "from a window, dark background, sharp focus on the eye and jawline.",
        "A view the single frontal canonical never shows. If the dropped angle "
        "references were earning anything, it should appear here.",
    ),
    Case(
        "low_light_motion",
        "Handheld night shot of a man turning quickly toward the camera under "
        "a streetlight, rain in the air, motion blur, high contrast.",
        "Low light, motion blur, and an off-axis turn at once -- the "
        "compound-stress case.",
    ),
)

ARMS = (
    ("1ref", 1, "the ADR-089 default"),
    ("4ref", 4, "the pre-ADR-089 behaviour"),
)


def _score(image: Path, reference: Path, character_id: str) -> tuple[float | None, str]:
    """Score with the same validator and settings the Identity Lab used."""

    from identity import validator as validator_module

    if not validator_module.DEEPFACE_AVAILABLE:
        return None, "unavailable"
    validator = validator_module.IdentityValidator(vision_fallback=None)
    result = validator.validate_image(
        str(image),
        str(reference),
        character_id=character_id,
        shot_type="portrait",
        threshold=IDENTITY_GATE,
    )
    if result.skipped or result.overall_score is None:
        return None, "unknown"
    return float(result.overall_score), "passed" if result.passed else "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--character", default=DEFAULT_CHARACTER)
    parser.add_argument("--out", default="logs/adr089-battery")
    parser.add_argument("--aspect", default="16:9")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated case keys, for re-running one cell",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="render only; useful when the scorer is unavailable",
    )
    args = parser.parse_args()

    project_path = Path("domain/projects") / args.project / "project.json"
    if not project_path.is_file():
        print(f"project not found: {project_path}")
        return 2
    project = json.loads(project_path.read_text(encoding="utf-8"))
    character = get_character(project, args.character)
    if not character:
        print(f"character not found: {args.character}")
        return 2

    canonical = _resolve_stored_media_path(
        project, character.get("canonical_reference", "")
    )
    angles = tuple(
        _resolve_stored_media_path(project, value)
        for value in (character.get("multi_angle_refs") or [])
    )
    spec = CharIdentitySpec(
        char_id=args.character,
        reference=canonical,
        identity_anchor=character.get("identity_anchor", ""),
        multi_angle_refs=angles,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = {key.strip() for key in args.only.split(",") if key.strip()}
    cases = [case for case in CASES if not selected or case.key in selected]
    if not cases:
        print(f"no cases matched --only={args.only!r}")
        return 2

    # The character record here carries only two angle refs, so the "4ref" arm
    # selects three images, not four. Report what was actually sent rather than
    # what was requested -- the arm label is the intent, the count is the fact.
    print(f"subject: {args.character}   canonical: {Path(canonical).name}")
    print(f"angles available: {len(angles)}  ({', '.join(Path(a).name for a in angles)})")
    print(f"aspect: {args.aspect}   seed: {args.seed}   cases: {len(cases)}\n")

    tracker = CostTracker(db_path=str(out_dir / "battery.db"), budget_usd=1.0)
    rows: list[dict[str, object]] = []
    try:
        for case in cases:
            for arm, cap, arm_note in ARMS:
                allocation = allocate_flux2_references(
                    primary=spec, secondaries=(), per_character_cap=cap
                )
                refs = list(allocation.reference_paths)
                target = out_dir / f"{case.key}__{arm}.png"
                label = f"{case.key} / {arm}"
                print(f"→ {label:<28} refs={len(refs)} ({arm_note})")
                started = time.monotonic()
                try:
                    run_flux2_klein_image_job(
                        prompt=case.prompt,
                        reference_image_paths=refs,
                        output_path=str(target),
                        seed=args.seed,
                        aspect_ratio=args.aspect,
                        cost_tracker=tracker,
                        request_id=f"adr089-battery-{case.key}-{arm}",
                        filename_prefix=f"adr089-{case.key}-{arm}",
                        poll_timeout_s=600.0,
                    )
                except Exception as exc:  # noqa: BLE001 - report, do not abort the battery
                    print(f"   FAILED: {type(exc).__name__}: {exc}")
                    rows.append({
                        "case": case.key, "arm": arm, "refs": len(refs),
                        "score": None, "verdict": "render_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue
                elapsed = time.monotonic() - started

                score: float | None = None
                verdict = "skipped"
                if not args.skip_scoring:
                    score, verdict = _score(target, Path(canonical), args.character)
                shown = "—" if score is None else f"{score:.3f}"
                print(f"   {elapsed:5.1f}s  score={shown}  {verdict}  → {target.name}")
                rows.append({
                    "case": case.key, "arm": arm, "refs": len(refs),
                    "seconds": round(elapsed, 1), "score": score,
                    "verdict": verdict, "output": target.name,
                })
    finally:
        tracker.close()

    summary = out_dir / "battery.json"
    summary.write_text(
        json.dumps(
            {
                "subject": args.character,
                "canonical": Path(canonical).name,
                "aspect_ratio": args.aspect,
                "seed": args.seed,
                "identity_gate": IDENTITY_GATE,
                "cases": {case.key: {"prompt": case.prompt, "why": case.why}
                          for case in cases},
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n{'case':<20} {'1ref':>8} {'4ref':>8}   winner")
    print("-" * 52)
    reversals = 0
    for case in cases:
        by_arm = {r["arm"]: r for r in rows if r["case"] == case.key}
        one, four = by_arm.get("1ref"), by_arm.get("4ref")
        s1 = one and one.get("score")
        s4 = four and four.get("score")
        f1 = "—" if s1 is None else f"{s1:.3f}"
        f4 = "—" if s4 is None else f"{s4:.3f}"
        if s1 is None or s4 is None:
            winner = "unscored"
        elif s1 >= s4:
            winner = "1ref"
        else:
            winner = "4ref  <-- REVERSAL"
            reversals += 1
        print(f"{case.key:<20} {f1:>8} {f4:>8}   {winner}")

    print(f"\nwrote {summary}")
    print(
        "\nRead the images before trusting the table. A score above "
        f"{IDENTITY_GATE} on a face that looks wrong is still a failure, and "
        "the scorer cannot see that."
    )
    if reversals:
        print(
            f"{reversals} case(s) favour the OLD behaviour. That is a lead about "
            "where one reference stops carrying, not a verdict -- one subject, "
            "one seed. Re-run those cells across several seeds before acting."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
