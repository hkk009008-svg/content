#!/usr/bin/env python3
"""Does hosted PuLID beat the local ceiling on realistic shots?

WHY
---
The archaeology (ADR-091 follow-up) found that the celebrated PuLID result --
"arc 0.6205 -> 0.8779, +0.257" -- does not survive its own record:

  * it was measured on a DIFFERENT character ("aria"), not this project's subject;
  * on FLUX.1-dev fp8, not the FLUX.2 Klein 4B this pipeline ships;
  * on a Novita 48 GB pod, not the `runpod-pulid-production` CI label;
  * its OFF baseline was called "coincidental prompt-match (generic woman, NOT
    aria's identity)" by the operator who ran it, so +0.257 is measured against
    an accidental floor;
  * the reference image and the acceptance artifact were gitignored and never
    committed, so the number is not reproducible -- only the method is.

Reviving the pod would mean standing up a second, non-commercially-licensed
base-model stack for a number that may not transfer. This probe answers the
only question that decides it, for roughly the price of a coffee: does PuLID,
on THIS subject and THESE realistic prompts, beat the local ceiling?

Local 16:9 numbers to beat (ADR-091, one reference, GhostFaceNet, per-shot gate):

    anchor 0.791 PASS | neutral_portrait 0.761 PASS | medium_action 0.648
    wide_small_face 0.576 PASS | profile_angled 0.569 | low_light_motion 0.562

OFF-ANGLE SCORES FROM THIS HARNESS ARE NOT EVIDENCE (ADR-092)
-------------------------------------------------------------
GhostFaceNet does not resolve identity on turned-away views, and in that band it
does not merely lose precision -- it INVERTS RANK. Measured 2026-08-08: the
subject's own real profile photograph scored 0.556, while a Kontext panel the
subject confirmed is NOT him scored 0.570. A stranger outranked the subject by
0.031.

So: any score below roughly 0.65 on a non-frontal shot carries no information
about identity. Do not compare two such numbers, do not call the higher one
better, and do not select references by score -- ranking the pool returns only
frontal images and discards the very views a video model needs.

Frontal measurements well above the band remain usable; that is where this
harness's anchor reproduces the lab's stored value to fifteen decimals.

COST -- THIS SPENDS REAL MONEY
------------------------------
fal charges $0.0333 per megapixel, rounded UP to the nearest megapixel.
`landscape_16_9` is 1280x720 = 0.92 MP -> 1 MP -> ~$0.0333 per image. Six
prompts is roughly $0.20. Run with `--limit 1` first (~$0.03) to confirm the
returned dimensions and the real per-image cost before committing to the rest.

    env -u GIT_INDEX_FILE .venv/bin/python scripts/adr089_hosted_pulid_probe.py --limit 1

CONFOUND, STATED UP FRONT
-------------------------
fal does not publish which FLUX.1 variant backs this endpoint, and this is a
different base model from local Klein 4B either way. So a win here is "this
hosted pipeline produces a better face than mine", NOT "PuLID contributes X".
That is the practical question; the isolated-contribution question would need an
OFF arm on the same host and is deliberately not asked yet.
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import web_server  # noqa: E402,F401  (TF before PyArrow)

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

from config.settings import settings  # noqa: E402
from domain.character_manager import (  # noqa: E402
    _resolve_stored_media_path,
    get_character,
)
from identity.types import get_threshold_for_shot  # noqa: E402


ENDPOINT = "fal-ai/flux-pulid"
PRICE_PER_MEGAPIXEL_USD = 0.0333
DEFAULT_PROJECT = "42c74e230519"
DEFAULT_CHARACTER = "hkkperson"

# The local battery's own numbers, for a like-for-like read.
LOCAL_16_9 = {
    "anchor": 0.791,
    "neutral_portrait": 0.761,
    "medium_action": 0.648,
    "wide_small_face": 0.576,
    "profile_angled": 0.569,
    "low_light_motion": 0.562,
}


def _battery_cases():
    """Reuse the battery's exact prompts and shot types -- same questions."""

    path = Path(_REPO_ROOT) / "scripts" / "adr089_prompt_battery.py"
    spec = importlib.util.spec_from_file_location("adr089_battery", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["adr089_battery"] = module  # dataclasses resolves through this
    spec.loader.exec_module(module)
    return module.CASES


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
        return None, "unknown", gate
    return float(result.overall_score), "passed" if result.passed else "failed", gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--character", default=DEFAULT_CHARACTER)
    parser.add_argument("--out", default="logs/adr089-hosted-pulid")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="render only the first N cases; use 1 for a cost/shape check first",
    )
    args = parser.parse_args()

    key = getattr(settings, "fal_key", "") or ""
    if not key:
        print("no fal key configured; nothing was spent")
        return 2
    os.environ.setdefault("FAL_KEY", key)
    import fal_client  # noqa: E402  (after FAL_KEY is set)

    project = json.loads(
        (Path("domain/projects") / args.project / "project.json").read_text("utf-8")
    )
    character = get_character(project, args.character)
    canonical = Path(
        _resolve_stored_media_path(project, character.get("canonical_reference", ""))
    )

    cases = list(_battery_cases())
    if args.limit:
        cases = cases[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"endpoint : {ENDPOINT}")
    print(f"reference: {canonical.name}")
    print(f"cases    : {len(cases)}   estimated ~${len(cases) * PRICE_PER_MEGAPIXEL_USD:.2f}"
          f" at 1 MP each (billing rounds UP)")
    print("uploading the reference once...")
    reference_url = fal_client.upload_file(str(canonical))
    print(f"  -> {reference_url[:72]}...\n")

    rows: list[dict] = []
    billed_megapixels = 0
    for case in cases:
        print(f"→ {case.key} ({case.shot_type})")
        started = time.monotonic()
        try:
            result = fal_client.subscribe(
                ENDPOINT,
                arguments={
                    "prompt": case.prompt,
                    "reference_image_url": reference_url,
                    "image_size": "landscape_16_9",
                    "seed": args.seed,
                    "num_inference_steps": 20,
                    "guidance_scale": 4.0,
                    "id_weight": 1.0,
                },
                with_logs=False,
            )
        except Exception as exc:  # noqa: BLE001 - report, keep going
            print(f"   FAILED: {type(exc).__name__}: {exc}")
            rows.append({"case": case.key, "score": None, "verdict": "render_failed",
                         "error": f"{type(exc).__name__}: {exc}"})
            continue
        elapsed = time.monotonic() - started

        image = (result.get("images") or [{}])[0]
        url = image.get("url")
        if not url:
            print("   FAILED: response carried no image url")
            rows.append({"case": case.key, "score": None, "verdict": "no_image"})
            continue
        width, height = image.get("width"), image.get("height")
        megapixels = -(-(width * height) // 1_000_000) if width and height else 1
        billed_megapixels += megapixels

        target = out_dir / f"{case.key}__hosted_pulid.png"
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())

        score, verdict, gate = _score(
            target, canonical, args.character, case.shot_type
        )
        shown = "—" if score is None else f"{score:.3f}"
        local = LOCAL_16_9.get(case.key)
        delta = "" if (score is None or local is None) else f"  ({score - local:+.3f} vs local)"
        print(f"   {elapsed:5.1f}s  {width}x{height} ~{megapixels}MP  score={shown}"
              f"  gate={gate:.2f}  {verdict}{delta}")
        rows.append({"case": case.key, "shot_type": case.shot_type, "gate": gate,
                     "seconds": round(elapsed, 1), "width": width, "height": height,
                     "megapixels": megapixels, "score": score, "verdict": verdict,
                     "local_16_9": local, "output": target.name})

    spent = billed_megapixels * PRICE_PER_MEGAPIXEL_USD
    (out_dir / "hosted.json").write_text(
        json.dumps({"endpoint": ENDPOINT, "seed": args.seed,
                    "reference": canonical.name,
                    "billed_megapixels": billed_megapixels,
                    "estimated_spend_usd": round(spent, 4),
                    "results": rows}, indent=2) + "\n", "utf-8")

    print(f"\n{'case':<20}{'gate':>6}{'local':>8}{'hosted':>8}{'delta':>9}   verdict")
    print("-" * 62)
    for row in rows:
        local = row.get("local_16_9")
        score = row.get("score")
        fmt = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
        d = "—" if (score is None or local is None) else f"{score - local:+.3f}"
        print(f"{row['case']:<20}{row.get('gate', 0):>6.2f}{fmt(local):>8}"
              f"{fmt(score):>8}{d:>9}   {row.get('verdict')}")

    print(f"\nbilled ~{billed_megapixels} MP -> estimated ${spent:.2f}"
          " (fal rounds each image UP to the next megapixel)")
    print(
        "Different base model from local Klein 4B, so read this as "
        "'does this pipeline give a better face', not 'PuLID contributes X'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
