#!/usr/bin/env python3
"""H4 — does leading VEO's reference list with the approved keyframe preserve
the approved composition?

THE CLAIM UNDER TEST (ADR-098)
------------------------------
The fal VEO branch built `image_urls` from `multi_angle_refs[:4]` and uploaded
the keyframe ONLY when that list came out empty. So on every shot whose
character had references, the frame the operator approved was discarded and the
video was generated from four face photographs plus prose. The fix puts the
keyframe first, inside the same four-image budget.

Nothing has established that this helps. This cell settles it.

WHY THIS ONE IS WORTH RENDERING
-------------------------------
Almost every claim in `docs/EVIDENCE-REGISTER.md` needs the operator's eye,
because ADR-092 removed the identity scorer for off-angle readings and no number
replaces taste. This claim is different: "did the keyframe reach the model?"
leaves a direct trace in the output. If the keyframe was used, frame 0 of the
clip should resemble it; if it was withheld, frame 0 is whatever the model
invented from face photographs. That is measurable without a face embedder.

THE DESIGN, AND THE TWO THINGS IT GETS RIGHT
--------------------------------------------
1. BOTH ARMS ANIMATE THE SAME KEYFRAME. The keyframe is generated once per shot
   and reused, so the only difference between arms is whether it reaches VEO.
   Generating a keyframe per arm would confound the thing under test with
   ordinary generation variance.

2. THE FLOOR IS MEASURED, NOT GUESSED. A third comparison scores each clip's
   frame 0 against the OTHER shot's keyframe. That is a pair with no
   relationship by construction, so it calibrates what "unrelated" scores on
   this data — and "markedly higher" stops being a threshold someone chose and
   becomes a distance from a measured floor.

   Without it, a delta of 0.2 would be uninterpretable. With it, the question
   is whether the withheld arm sits at the unrelated floor.

WHAT IS RECONSTRUCTED, AND WHY THAT IS HONEST
---------------------------------------------
The `keyframe_led` arm calls the shipped `generate_ai_video`, so its result is
evidence about the code that ships. The `references_only` arm CANNOT: that
behaviour was deleted by ADR-098. It is reconstructed here as a direct call to
the same fal endpoint with the exact `image_urls` the old code would have
built — faces only, no keyframe. A control for removed behaviour has to be
reconstructed or there is no control at all; what matters is that the
reconstruction is small, visible, and stated.

COST
----
2 keyframes (FLUX_KONTEXT) + 4 clips (VEO). Priced by `evidence_harness.py`,
which reads `API_COST_USD` rather than repeating a number here.

WHAT THIS DOES NOT COVER
------------------------
* Only fal VEO. Every other provider already sent the keyframe, so there is
  nothing to compare on them; that enumeration is in ADR-098.
* Two shots on one subject. A reversal on one shot is a lead, not a verdict.
* Whether the face lost by giving VEO one fewer reference costs anything. That
  is a different question, needs the operator's eye, and is registered as part
  of H3 rather than smuggled in here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from domain.evidence_metrics import palette_match, structure_match  # noqa: E402

# Two shots of one scene. Deliberately ordinary director prose: the claim is
# about plumbing, and a prompt that begged for composition fidelity would help
# the withheld arm cheat.
#: VEO 3.1 reference-to-video accepts ONLY this value — a "4s" reconstruction
#: was rejected outright by the provider. It matches the shipped default at
#: phase_c_ffmpeg.py:264, which matters twice: the arms must agree, and the
#: control must reproduce the real call rather than a plausible-looking one.
_VEO_DURATION = "8s"

SHOTS = [
    {
        "id": "h4_shot_a",
        "prompt": (
            "[SHOT] Medium shot, 50mm. [SCENE] A quiet kitchen at first light, "
            "pale window light from the left, mugs on the counter. "
            "[ACTION] standing at the counter, turning slightly toward the window."
        ),
        "camera": "slow_push_in",
    },
    {
        "id": "h4_shot_b",
        "prompt": (
            "[SHOT] Wide shot, 35mm. [SCENE] The same kitchen, the doorway and "
            "the far wall visible, morning light across the floor. "
            "[ACTION] walking in from the hallway."
        ),
        "camera": "static",
    },
]


def _load(path: str) -> np.ndarray:
    """BGR from cv2 -> RGB. Both metrics are channel-order sensitive."""

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"could not read image: {path}")
    return image[:, :, ::-1]


def first_frame(video_path: str, output_path: str) -> np.ndarray:
    """Frame 0 — the frame a start image or lead reference most influences."""

    capture = cv2.VideoCapture(str(video_path))
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"no readable first frame in {video_path}")
    cv2.imwrite(str(output_path), frame)
    return frame[:, :, ::-1]


def compare(frame: np.ndarray, keyframe: np.ndarray) -> dict:
    return {
        "structure_match": round(structure_match(frame, keyframe), 4),
        "palette_match": round(palette_match(frame, keyframe), 4),
    }


def verdict(rows: list[dict]) -> dict:
    """Read the three numbers together, and refuse to over-read them.

    `led` should sit well above `floor`. The question is where `withheld` sits:
    at the floor means the keyframe was genuinely absent from that render and
    present in the other, which is the claim. Near `led` means reference ORDER
    does not matter to this provider and the fix is inert — worth knowing, and
    the opposite of what ADR-098 assumed.
    """

    def mean(key: str) -> float:
        values = [row[key] for row in rows if row.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0

    led, withheld, floor = mean("led"), mean("withheld"), mean("floor")
    span = led - floor
    if span <= 0.05:
        reading = (
            "INCONCLUSIVE — the measured floor is not far below the keyframe-led "
            "arm, so this data cannot separate 'used the keyframe' from "
            "'did not'. Do not read the arm difference."
        )
    elif withheld <= floor + 0.25 * span:
        reading = (
            "SUPPORTS the claim — the withheld arm sits at the unrelated floor, "
            "so the approved composition was reaching VEO only in the fixed arm."
        )
    elif withheld >= floor + 0.75 * span:
        reading = (
            "REFUTES the claim as stated — the withheld arm scores close to the "
            "keyframe-led arm, so reference ORDER is not what carried the "
            "composition and the ADR-098 fix may be inert."
        )
    else:
        reading = (
            "PARTIAL — the withheld arm sits between the floor and the led arm. "
            "The keyframe helps and is not the only thing carrying composition."
        )
    return {
        "led_mean": led, "withheld_mean": withheld, "floor_mean": floor,
        "span": round(span, 4), "reading": reading,
    }


def main() -> int:
    print(__doc__)
    print("\nThis module is the measurement half of H4 and is import-safe.")
    print("Rendering is driven by scripts/evidence_harness.py, which owns the")
    print("spend authorisation. Nothing here spends money on import or on a")
    print("bare run.\n")
    print(f"shots configured: {[shot['id'] for shot in SHOTS]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Rendering. Only reached from evidence_harness.py, which owns the spend
# authorisation; importing this module renders nothing.
# ---------------------------------------------------------------------------

def _reconstructed_pre_fix_veo_call(fal_client, keyframe, refs, prompt, out_mp4):
    """The behaviour ADR-098 removed, rebuilt as the control arm.

    Deliberately NOT a call into the shipped code, because the shipped code no
    longer does this. It reproduces exactly what the old branch built —
    `image_urls` from the references only, keyframe withheld — against the same
    endpoint with the same payload shape. Kept small and in one place so it is
    obvious what is being reconstructed and easy to check against the diff.
    """

    image_urls = [fal_client.upload_file(ref) for ref in refs[:4] if os.path.exists(ref)]
    if not image_urls:
        # The one case the old code got right: with no references it did send
        # the keyframe. Reproduce that too, or the control would be an empty call.
        image_urls = [fal_client.upload_file(keyframe)]
    result = fal_client.subscribe(
        "fal-ai/veo3.1/reference-to-video",
        arguments={
            "prompt": prompt,
            "image_urls": image_urls,
            "aspect_ratio": "16:9",
            "duration": _VEO_DURATION,
            "resolution": "720p",
            "generate_audio": False,
        },
    )
    url = (result or {}).get("video", {}).get("url")
    if not url:
        raise RuntimeError("reconstructed VEO call returned no video url")
    from performance._net import safe_download
    if safe_download(url, out_mp4, max_bytes=256 * 1024 * 1024,
                     allowed_content_types=("video/mp4",)) is None:
        raise RuntimeError("reconstructed VEO clip failed download validation")
    return out_mp4


def render_and_measure(project_id: str, out_dir: Path, *, dry_run: bool) -> dict:
    """Render both arms of both shots and return the manifest.

    `dry_run` renders nothing and returns the plan — used by the harness to
    prove the wiring resolves real assets before any money moves.
    """

    from domain.project_manager import load_project
    from domain.character_manager import get_multi_angle_refs, get_reference_image

    project = load_project(project_id)
    if not project or not project.get("characters"):
        raise RuntimeError(f"project {project_id} has no character to render")
    character = project["characters"][0]
    refs = [r for r in get_multi_angle_refs(project, character["id"]) if os.path.exists(r)]
    canonical = get_reference_image(project, character["id"])
    if not refs or not canonical or not os.path.exists(canonical):
        raise RuntimeError("character has no usable references on disk")

    manifest = {
        "hypothesis": "H4",
        "project_id": project_id,
        "character_id": character["id"],
        "references_available": len(refs),
        "shots": [],
        "dry_run": dry_run,
    }
    if dry_run:
        manifest["note"] = (
            "assets resolved; no provider call made and nothing spent"
        )
        return manifest

    out_dir.mkdir(parents=True, exist_ok=True)
    import fal_client
    from phase_c_assembly import generate_ai_broll
    from phase_c_ffmpeg import generate_ai_video

    keyframes: dict[str, str] = {}
    for shot in SHOTS:
        keyframe = str(out_dir / f"{shot['id']}_keyframe.jpg")
        if os.path.exists(keyframe) and os.path.getsize(keyframe) > 0:
            # Already paid for on an earlier attempt. Reusing it is not just
            # thrift: a retry that regenerates the keyframe changes the very
            # thing both arms are measured against, so the numbers would not be
            # comparable with the attempt that produced it.
            print(f"   [H4] reusing existing keyframe: {keyframe}")
            keyframes[shot["id"]] = keyframe
            continue
        # ONE keyframe per shot, shared by both arms. Generating one per arm
        # would confound the thing under test with generation variance.
        result = generate_ai_broll(
            shot["prompt"], keyframe,
            seed=20260808,
            character_image=canonical,
            multi_angle_refs=refs,
            identity_anchor=character.get("name", ""),
        )
        if not result or not os.path.exists(keyframe):
            raise RuntimeError(f"keyframe generation failed for {shot['id']}")
        keyframes[shot["id"]] = keyframe

    rows = []
    for shot in SHOTS:
        keyframe = keyframes[shot["id"]]
        other = keyframes[next(s["id"] for s in SHOTS if s["id"] != shot["id"])]

        led_mp4 = str(out_dir / f"{shot['id']}_led.mp4")
        produced = generate_ai_video(
            keyframe, shot["camera"], "VEO", led_mp4,
            character_id=character["id"], multi_angle_refs=refs,
            shot_type="medium", video_fallbacks=["VEO"],
            duration=_VEO_DURATION,
        )
        # generate_ai_video returns None on failure rather than raising. The
        # return was ignored in the first version, so a silently failed arm
        # walked on and the run died later in the OTHER arm — pointing at the
        # wrong code. An unchecked return is how a failure gets misattributed.
        if not produced or not os.path.exists(led_mp4):
            raise RuntimeError(
                f"keyframe-led VEO arm produced no clip for {shot['id']}; "
                "see the provider cascade output above"
            )
        withheld_mp4 = str(out_dir / f"{shot['id']}_withheld.mp4")
        _reconstructed_pre_fix_veo_call(
            fal_client, keyframe, refs, shot["prompt"], withheld_mp4,
        )

        keyframe_image = _load(keyframe)
        other_image = _load(other)
        led_frame = first_frame(led_mp4, str(out_dir / f"{shot['id']}_led_f0.jpg"))
        withheld_frame = first_frame(
            withheld_mp4, str(out_dir / f"{shot['id']}_withheld_f0.jpg")
        )
        row = {
            "shot": shot["id"],
            "led": compare(led_frame, keyframe_image)["structure_match"],
            "withheld": compare(withheld_frame, keyframe_image)["structure_match"],
            # The measured floor: this clip against the OTHER shot's keyframe,
            # a pair unrelated by construction.
            "floor": compare(led_frame, other_image)["structure_match"],
            "palette": {
                "led": compare(led_frame, keyframe_image)["palette_match"],
                "withheld": compare(withheld_frame, keyframe_image)["palette_match"],
            },
        }
        rows.append(row)
        manifest["shots"].append(row)

    manifest["verdict"] = verdict(rows)
    return manifest
