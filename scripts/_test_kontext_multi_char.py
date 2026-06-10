"""S1 spike — does fal-ai/flux-pro/kontext/max/multi separate two identities?

Five calls sharing one scene (spec §6; criteria revised per Lane-V V-3/V-4):
  1. baseline : primary face only, today's single-char prompt shape
  2. control  : NO secondary ref — both characters text-described (the floor)
  3-5. multi_a/b/c : both faces in image_urls, @Image1/@Image2 PRESERVE blocks
       (N=3 — this tier is unseeded; N=1-2 can NO-GO on output variance alone)

Scores every output against both refs with the shared GhostFaceNet validator and
prints the verdict. Per-arm GO:
  GO     : secondary >= control_secondary + 0.10
           AND secondary >= 0.45 (S1_SECONDARY_FLOOR — the bottom of spec
           §3(a)'s projected 0.45-0.60 band; the per-shot-type lenient
           threshold is printed as ADVISORY context, never gated on — V-3)
           AND |primary - baseline_primary| <= 0.05
           AND no blend signal (both faces of the arm in the 0.40-0.50 band;
           blend deliberately OVERRIDES the floor in the [0.45, 0.50) overlap —
           both-faces-in-band means the lift is an averaging artifact)
Overall S1 verdict = MAJORITY of the three multi arms (>= 2/3 GO).

DRY-RUN by default (prints the five payloads, no spend). --live costs ~5 x $0.04
~= $0.20 (flat-rate assumption unverified; the control call rides
fal-ai/flux-pro/v1.1-ultra whose price may differ — read the real per-call
prices off the FAL dashboard while the calls are visible there, spec §4).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from identity.types import get_threshold_for_shot

# V-3: absolute go-floor — bottom of spec §3(a)'s projected band (numerically the
# wide-shot lenient threshold, identity/types.py:98). The --shot-type lenient
# threshold sits INSIDE the projected band and would false-veto a real lift.
S1_SECONDARY_FLOOR = 0.45


def build_prompts(scene: str, anchor_a: str, anchor_b: str) -> dict:
    quality = (
        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
        "shallow depth of field with circular bokeh, natural film grain ISO 400."
    )
    single = (
        f"PRESERVE IDENTITY: The person from @Image1 is {anchor_a}. "
        f"Keep this EXACT face, hair, eye color, skin tone unchanged. "
        f"CHANGE BACKGROUND: {scene}. SET POSE: both people talking, facing each "
        f"other. SET CAMERA: Medium two-shot, 50mm lens. "
        f"CONSTRAINTS: The face in the output MUST match @Image1 exactly. {quality}"
    )
    control = (
        f"Two people in {scene}: on the left, {anchor_a}; on the right, {anchor_b}. "
        f"Medium two-shot, 50mm lens, both talking, facing each other. {quality}"
    )
    multi = (
        f"PRESERVE IDENTITY: The person from @Image1 is {anchor_a}. Keep this EXACT "
        f"face, hair, eye color, skin tone unchanged. "
        f"PRESERVE IDENTITY: The person from @Image2 is {anchor_b}. Keep this EXACT "
        f"face, hair, eye color, skin tone unchanged. "
        f"CHANGE BACKGROUND: {scene}. SET POSE: both people talking, facing each "
        f"other; the person from @Image1 on the left, the person from @Image2 on "
        f"the right. SET CAMERA: Medium two-shot, 50mm lens. "
        f"CONSTRAINTS: Do NOT blend or average the two faces. Each output face MUST "
        f"match its own reference image exactly. {quality}"
    )
    return {"baseline": single, "control": control, "multi": multi}


def score(img_path: str, ref_path: str, char_id: str) -> float:
    from identity import get_shared_validator
    r = get_shared_validator().validate_image(
        img_path, ref_path, character_id=char_id, threshold=0.0
    )
    # overall_score is None iff validation was skipped (identity/types.py:68);
    # treat that as 0.0 so the verdict math never crashes mid-spike.
    return r.overall_score or 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--char-a", required=True, help="primary reference image path")
    ap.add_argument("--char-b", required=True, help="secondary reference image path")
    ap.add_argument("--anchor-a", default="the woman in the first reference photo")
    ap.add_argument("--anchor-b", default="the woman in the second reference photo")
    ap.add_argument("--scene", default="a quiet rooftop cafe at dusk")
    ap.add_argument("--shot-type", default="medium",
                    choices=["portrait", "medium", "wide", "action"])
    ap.add_argument("--outdir", default="logs/s1_kontext_multichar")
    ap.add_argument("--live", action="store_true",
                    help="actually call FAL (~5 x $0.04 ~= $0.20). Default: dry-run.")
    args = ap.parse_args()

    prompts = build_prompts(args.scene, args.anchor_a, args.anchor_b)
    calls = [
        ("baseline", prompts["baseline"], [args.char_a]),
        ("control", prompts["control"], []),
        ("multi_a", prompts["multi"], [args.char_a, args.char_b]),
        ("multi_b", prompts["multi"], [args.char_a, args.char_b]),
        ("multi_c", prompts["multi"], [args.char_a, args.char_b]),
    ]

    if not args.live:
        for name, prompt, refs in calls:
            print(f"--- {name} (refs: {len(refs)}) ---\n{prompt}\n")
        print("DRY RUN — re-run with --live to spend (~$0.20).")
        return 0

    import fal_client
    os.makedirs(args.outdir, exist_ok=True)
    results = {}
    for name, prompt, refs in calls:
        arguments = {
            "prompt": prompt,
            "guidance_scale": 3.5,
            "aspect_ratio": "16:9",
            "output_format": "jpeg",
            "num_images": 1,
        }
        if refs:
            arguments["image_urls"] = [fal_client.upload_file(r) for r in refs]
            endpoint = "fal-ai/flux-pro/kontext/max/multi"
        else:
            endpoint = "fal-ai/flux-pro/v1.1-ultra"
            arguments.pop("guidance_scale")
        out = os.path.join(args.outdir, f"{name}.jpg")
        res = fal_client.subscribe(endpoint, client_timeout=FAL_TIMEOUT_IMAGE_S,
                                   arguments=arguments)
        import urllib.request
        urllib.request.urlretrieve(res["images"][0]["url"], out)
        results[name] = {
            "path": out,
            "score_a": score(out, args.char_a, "spike_char_a"),
            "score_b": score(out, args.char_b, "spike_char_b"),
        }
        print(f"{name}: a={results[name]['score_a']:.3f} "
              f"b={results[name]['score_b']:.3f}  {out}")

    lenient = get_threshold_for_shot(args.shot_type, mode="lenient")
    base_a = results["baseline"]["score_a"]
    ctrl_b = results["control"]["score_b"]
    verdicts = []
    for name in ("multi_a", "multi_b", "multi_c"):
        a, b = results[name]["score_a"], results[name]["score_b"]
        blend = 0.40 <= a <= 0.50 and 0.40 <= b <= 0.50
        go = (b >= ctrl_b + 0.10) and (b >= S1_SECONDARY_FLOOR) \
            and (abs(a - base_a) <= 0.05) and not blend
        verdicts.append(go)
        print(f"{name}: {'GO' if go else 'NO-GO'}"
              f" (b vs control+0.10: {b:.3f} vs {ctrl_b + 0.10:.3f};"
              f" floor={S1_SECONDARY_FLOOR};"
              f" advisory lenient[{args.shot_type}]={lenient} — not gated;"
              f" |a-base|={abs(a - base_a):.3f}; blend={blend})")
    print(json.dumps(results, indent=1))
    spread = [round(results[n]["score_b"], 3)
              for n in ("multi_a", "multi_b", "multi_c")]
    print("S1 VERDICT:", "GO" if sum(verdicts) >= 2 else "NO-GO",
          f"(majority of 3 arms; secondary spread {spread} — V-4: N=3 has power"
          " for separation-vs-blend, not fine threshold effects)",
          "— record in spec §6 + ARCHITECTURE-adjacent ADR per spec AC5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
