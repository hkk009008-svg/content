"""Arc-score the §7.2 bundle session artifacts locally (runbook exit step).

For each artifact, score identity vs EACH character's reference via
IdentityValidator.validate_image (DeepFace/ArcFace; best-face match per
reference, so a two-shot yields per-character scores from two calls).
Bleed (spec §S3) shows as PAIRED collapse: both characters' scores dropping
together on the same arm.

Run: PYTHONPATH=. .venv/bin/python scripts/_arc_score_session.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identity.validator import IdentityValidator

ARIA_REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
MAN_REF = "logs/p12_fresh_face_man.jpg"

ARTIFACTS = [
    # (path, refs-to-score: a=aria m=man)
    ("logs/max_lora_live_check.jpg", "a"),       # Phase-2 single-char Aria
    ("logs/pass_a_multichar_FAILED_landscape_20260610.jpg", "am"),  # failure record
    ("logs/pass_a_multichar.jpg", "am"),         # Pass-A post-fix
    ("logs/s2_dual_n1.jpg", "am"),
    ("logs/s2_dual_n2.jpg", "am"),
    ("logs/s2_dual_n3.jpg", "am"),
    ("logs/s2_dual_n4.jpg", "am"),
    ("logs/s3_stack_sec35.jpg", "am"),
    ("logs/s3_stack_sec45.jpg", "am"),
    ("logs/s3_stack_sec55.jpg", "am"),
]


def main():
    v = IdentityValidator()
    rows = []
    for path, refs in ARTIFACTS:
        if not os.path.exists(path):
            rows.append((path, None, None, "MISSING"))
            continue
        aria = man = None
        if "a" in refs:
            aria = v.validate_image(path, ARIA_REF, "aria", shot_type="medium").overall_score
        if "m" in refs:
            man = v.validate_image(path, MAN_REF, "man", shot_type="medium").overall_score
        rows.append((path, aria, man, ""))
    print("\n=== ARC SCORE TABLE (best-face match per reference) ===")
    print(f"{'artifact':56s} {'aria':>6s} {'man':>6s}")
    for path, aria, man, note in rows:
        a = f"{aria:.3f}" if aria is not None else "  —  "
        m = f"{man:.3f}" if man is not None else "  —  "
        print(f"{path:56s} {a:>6s} {m:>6s} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
