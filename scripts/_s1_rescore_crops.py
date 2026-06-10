"""S1 per-face re-score — fixes the face-pick ambiguity in the first S1 pass.

Spec §6 says "score every output FACE"; the spike script scored every output
IMAGE, letting the validator pick an arbitrary face out of the two-shot. This
re-scores the EXISTING S1 outputs (no new spend) on half-frame crops so each
crop contains exactly one face: left↔char-a, right↔char-b per the prompt's
stated layout, plus the cross terms as a face-swap check. Verdict math is the
same pre-registered e57f9ef criteria applied to the corrected measurement.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from scripts._test_kontext_multi_char import S1_SECONDARY_FLOOR


def crop_half(img_path: str, side: str, outdir: str) -> str:
    img = Image.open(img_path)
    w, h = img.size
    box = (0, 0, w // 2, h) if side == "left" else (w // 2, 0, w, h)
    out = os.path.join(
        outdir, f"{os.path.splitext(os.path.basename(img_path))[0]}_{side}.jpg"
    )
    img.crop(box).save(out, quality=95)
    return out


def score(img_path: str, ref_path: str, char_id: str) -> float:
    from identity import get_shared_validator
    r = get_shared_validator().validate_image(
        img_path, ref_path, character_id=char_id, threshold=0.0
    )
    return r.overall_score or 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--char-a", required=True)
    ap.add_argument("--char-b", required=True)
    ap.add_argument("--indir", default="logs/s1_kontext_multichar")
    args = ap.parse_args()

    outdir = os.path.join(args.indir, "crops")
    os.makedirs(outdir, exist_ok=True)

    names = ["baseline", "control", "multi_a", "multi_b", "multi_c"]
    results = {}
    for name in names:
        src = os.path.join(args.indir, f"{name}.jpg")
        left = crop_half(src, "left", outdir)
        right = crop_half(src, "right", outdir)
        results[name] = {
            "left_vs_a": score(left, args.char_a, "crop_a"),
            "right_vs_b": score(right, args.char_b, "crop_b"),
            # cross terms: high values here relative to the diagonal = faces
            # swapped or identity leaked across slots
            "left_vs_b": score(left, args.char_b, "crop_xb"),
            "right_vs_a": score(right, args.char_a, "crop_xa"),
        }
        r = results[name]
        print(f"{name}: L/a={r['left_vs_a']:.3f} R/b={r['right_vs_b']:.3f}"
              f"  [cross L/b={r['left_vs_b']:.3f} R/a={r['right_vs_a']:.3f}]")

    base_a = results["baseline"]["left_vs_a"]
    ctrl_b = results["control"]["right_vs_b"]
    verdicts = []
    for name in ("multi_a", "multi_b", "multi_c"):
        a = results[name]["left_vs_a"]
        b = results[name]["right_vs_b"]
        blend = 0.40 <= a <= 0.50 and 0.40 <= b <= 0.50
        go = (b >= ctrl_b + 0.10) and (b >= S1_SECONDARY_FLOOR) \
            and (abs(a - base_a) <= 0.05) and not blend
        verdicts.append(go)
        print(f"{name}: {'GO' if go else 'NO-GO'}"
              f" (b vs control+0.10: {b:.3f} vs {ctrl_b + 0.10:.3f};"
              f" floor={S1_SECONDARY_FLOOR};"
              f" |a-base|={abs(a - base_a):.3f}; blend={blend})")
    print(json.dumps(results, indent=1))
    print("S1 CORRECTED VERDICT:", "GO" if sum(verdicts) >= 2 else "NO-GO",
          "(per-face measurement; same pre-registered criteria)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
