#!/usr/bin/env python3
"""Generate Kontext panels from a CHOSEN source photo, not always the canonical.

WHY
---
`_generate_multi_angle_refs` always edits from the canonical front close-up. That
means every generated panel — including `angle_profile` — descends from one
frontal photograph, and a frontal photograph does not contain the side of a
head. The generated profile scored 0.570; the subject's REAL profile photograph
scored 0.556. Both sit at the scorer's floor, so the numbers cannot separate
them, but only one of them contains real profile geometry.

The subject has four real photographs: front close-up, front wide, left profile,
right three-quarter. Three of them are unused as GENERATION SOURCES. Editing
from a real profile should preserve real profile geometry while adding lighting
or expression variety, which is coverage a frontal-derived panel cannot supply.

This produces coverage the existing generator structurally cannot.

READ THE RESULT WITH YOUR EYES
------------------------------
GhostFaceNet floors near 0.56 on ANY profile, including real photographs of the
subject. A profile panel's score is therefore close to meaningless. The score is
reported only to catch gross drift; whether the panel is a usable reference is a
judgement the scorer cannot make. Look at the images.

COSTS REAL MONEY: $0.08 per panel through the durable paid-attempt ledger.

    env -u GIT_INDEX_FILE .venv/bin/python scripts/generate_panels_from_source.py --dry-run
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
from paid_provider import paid_attempt_id, request_fingerprint  # noqa: E402
from performance._net import safe_download  # noqa: E402


CHAR_DIR = Path("domain/projects/42c74e230519/characters")

# Each job names its SOURCE explicitly. The point is coverage the canonical
# cannot produce, so every prompt here is a MINIMAL edit that preserves the
# source's pose while varying something else.
JOBS = (
    {
        "name": "profile_outdoor",
        "source": "hkkperson_angle_left_profile.jpg",
        "prompt": (
            "Keep this exact person's face, hair, skin and all physical features "
            "identical. Keep the same side-profile head angle. Change only the "
            "lighting to natural outdoor daylight with soft shadows. "
            "Photorealistic portrait, 8K."
        ),
        "why": "A profile with real geometry plus lighting variety — the frontal "
               "canonical cannot produce this at all.",
    },
    {
        "name": "threequarter_smile",
        "source": "hkkperson_angle_right_threequarter.jpg",
        "prompt": (
            "Keep this exact person's face, hair, skin and all physical features "
            "identical. Keep the same three-quarter head angle. Change only the "
            "expression to a warm genuine smile with slightly crinkled eyes. "
            "Photorealistic portrait, 8K."
        ),
        "why": "A smiling three-quarter — an angle and expression combination "
               "that exists in no current reference.",
    },
)


def _score(image: Path, reference: Path):
    from identity import validator as vm

    gate = get_threshold_for_shot("portrait")
    if not vm.DEEPFACE_AVAILABLE:
        return None, gate
    result = vm.IdentityValidator(vision_fallback=None).validate_image(
        str(image), str(reference), character_id="hkkperson",
        shot_type="portrait", threshold=gate,
    )
    if result.skipped or result.overall_score is None:
        return None, gate
    return float(result.overall_score), gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="logs/source-panels")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    canonical = CHAR_DIR / "hkkperson_canonical_front_closeup.jpg"
    total = cm._FLUX_KONTEXT_COST_USD * len(JOBS)
    print(f"engine : {cm._FLUX_KONTEXT_APPLICATION}")
    print(f"cost   : {len(JOBS)} x ${cm._FLUX_KONTEXT_COST_USD:.2f} = ${total:.2f}\n")
    for job in JOBS:
        print(f"  {job['name']:<22} from {job['source']}")
        print(f"      {job['why']}")
    print()
    if args.dry_run:
        print("dry run — nothing spent, nothing written")
        return 0

    if not cm.FAL_AVAILABLE or not getattr(cm.settings, "fal_key", ""):
        print("FAL unavailable or no key. Stopping rather than skipping silently.")
        return 2
    import fal_client

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker(db_path=str(out_dir / "source.db"), budget_usd=2.0)
    rows = []
    try:
        for job in JOBS:
            source = CHAR_DIR / job["source"]
            if not source.is_file():
                print(f"{job['name']}: source missing, skipped")
                continue
            recipe = {
                "prompt": job["prompt"],
                "guidance_scale": 4.0,
                "aspect_ratio": "3:4",
                "output_format": "jpeg",
                "num_images": 1,
            }
            fingerprint = request_fingerprint(
                "character-source-panel-v1", cm._FLUX_KONTEXT_APPLICATION,
                cm.file_fingerprint(str(source)), job["name"], recipe,
            )
            attempt = paid_attempt_id(
                "character-source-panel", "sheet-hkkperson", "hkkperson",
                job["name"], fingerprint,
            )
            print(f"→ {job['name']}  (source: {source.name})")
            started = time.monotonic()
            url = fal_client.upload_file(str(source))
            result = cm.run_durable_fal_job(
                application=cm._FLUX_KONTEXT_APPLICATION,
                arguments={**recipe, "image_urls": [url]},
                attempt_id=attempt,
                engine=cm._FLUX_KONTEXT_ENGINE,
                operation=cm._FLUX_KONTEXT_OPERATION,
                estimated_cost_usd=cm._FLUX_KONTEXT_COST_USD,
                request_fingerprint_value=fingerprint,
                cost_tracker=tracker,
                shot_id="hkkperson",
                video_id="sheet-hkkperson",
                poll_timeout_s=cm.FAL_TIMEOUT_IMAGE_S,
            )
            images = (result or {}).get("images") or []
            img_url = images[0].get("url") if images else None
            if not img_url:
                print("   FAILED: no image url returned")
                continue
            target = CHAR_DIR / f"{job['name']}.jpg"
            if safe_download(
                img_url, str(target), max_bytes=64 * 1024 * 1024,
                allowed_content_types=("image/jpeg",),
                content_validator=lambda p: cm.validate_image_artifact(
                    p, expected_formats=("JPEG",)
                ),
            ) is None:
                print("   FAILED: download validation")
                continue
            elapsed = time.monotonic() - started
            score, gate = _score(target, canonical)
            shown = "—" if score is None else f"{score:.3f}"
            print(f"   {elapsed:5.1f}s  score={shown} (gate {gate:.2f})"
                  f"  -> {target.name}")
            rows.append({"name": job["name"], "source": job["source"],
                         "score": score, "output": target.name})
    finally:
        tracker.close()

    (out_dir / "source_panels.json").write_text(
        json.dumps({"spend_usd": round(total, 2), "panels": rows}, indent=2) + "\n",
        "utf-8",
    )
    print(f"\nspent ~${total:.2f}")
    print(
        "Scores near 0.56 on a profile are the instrument's FLOOR — the subject's\n"
        "own real profile photograph scores 0.556. Judge these by eye: does the\n"
        "pose survive, and is it still unmistakably the same person?"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
