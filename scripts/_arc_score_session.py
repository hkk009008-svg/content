"""Arc-score the §7.2 bundle session artifacts locally (runbook exit step).

For each artifact, score identity vs EACH character's reference via
IdentityValidator.validate_image (DeepFace/ArcFace; best-face match per
reference, so a two-shot yields per-character scores from two calls).
Bleed (spec §S3) shows as PAIRED collapse: both characters' scores dropping
together on the same arm.

Default mode: score each full artifact.
Halves mode (--halves): crop L/R halves (w//2 boundary, same as
_s1_rescore_crops.crop_half) and score EACH half against EACH ref (man + aria).
Emits logs/halves_rescore_YYYYMMDD.json + logs/halves_rescore_YYYYMMDD.txt.

Run: PYTHONPATH=. .venv/bin/python scripts/_arc_score_session.py
Halves: PYTHONPATH=. .venv/bin/python scripts/_arc_score_session.py --halves
"""
import argparse
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

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

# Artifacts scored in halves mode (all dual-char artifacts)
HALVES_ARTIFACTS = [
    "logs/pass_a_multichar_FAILED_landscape_20260610.jpg",
    "logs/pass_a_multichar.jpg",
    "logs/s2_dual_n1.jpg",
    "logs/s2_dual_n2.jpg",
    "logs/s2_dual_n3.jpg",
    "logs/s2_dual_n4.jpg",
    "logs/s3_stack_sec35.jpg",
    "logs/s3_stack_sec45.jpg",
    "logs/s3_stack_sec55.jpg",
]


def collect_halves_artifacts(patterns: list[str] | None = None) -> list[str]:
    """Return the ordered list of artifact paths for halves mode.

    `patterns` (paths or glob patterns) overrides the default §7.2 pod-arc
    set — required so future spikes (e.g. Pass-B Phase 3) score their own
    artifacts with this same committed instrument (R-MEASURE).
    """
    if patterns:
        return [p for pat in patterns for p in (sorted(glob.glob(pat)) or [pat])]
    return list(HALVES_ARTIFACTS)


def format_halves_table(rows: list[dict]) -> str:
    """Format halves-mode rows into a human-readable table.

    Each row dict: artifact, half, ref, arc_score (float or None), note (str).
    Returns a multi-line string.
    """
    header = f"{'artifact':56s} {'half':5s} {'ref':5s} {'arc':>6s}"
    divider = "-" * len(header)
    lines = [
        "=== HALVES MODE ARC SCORE TABLE (w//2 boundary, best-face per ref) ===",
        header,
        divider,
    ]
    for r in rows:
        score_str = f"{r['arc_score']:.3f}" if r["arc_score"] is not None else "  —  "
        note = f"  {r['note']}" if r.get("note") else ""
        lines.append(
            f"{r['artifact']:56s} {r['half']:5s} {r['ref']:5s} {score_str:>6s}{note}"
        )
    return "\n".join(lines)


def crop_half(img_path: str, side: str, outdir: str) -> str:
    """Crop image to left or right half (w//2 boundary). Reuses _s1_rescore_crops logic."""
    img = Image.open(img_path)
    w, h = img.size
    box = (0, 0, w // 2, h) if side == "left" else (w // 2, 0, w, h)
    out = os.path.join(
        outdir,
        f"{os.path.splitext(os.path.basename(img_path))[0]}_{side}.jpg",
    )
    img.crop(box).save(out, quality=95)
    return out


def run_halves(
    v: IdentityValidator,
    outdir: str,
    date_suffix: str,
    artifact_patterns: list[str] | None = None,
) -> int:
    """Run halves mode: crop L/R, score each half vs each ref, emit artifacts."""
    artifact_paths = collect_halves_artifacts(artifact_patterns)
    crop_dir = os.path.join(outdir, "halves_crops")
    os.makedirs(crop_dir, exist_ok=True)

    rows: list[dict] = []
    for path in artifact_paths:
        if not os.path.exists(path):
            for side in ("left", "right"):
                for ref_name in ("man", "aria"):
                    rows.append({
                        "artifact": path,
                        "half": side,
                        "ref": ref_name,
                        "arc_score": None,
                        "note": "MISSING",
                    })
            continue

        for side in ("left", "right"):
            crop_path = crop_half(path, side, crop_dir)
            for ref_name, ref_path in (("man", MAN_REF), ("aria", ARIA_REF)):
                try:
                    result = v.validate_image(
                        crop_path, ref_path, ref_name, shot_type="medium"
                    )
                    arc = result.overall_score
                except Exception as exc:
                    arc = None
                    note = f"ERROR: {exc}"
                else:
                    note = ""
                rows.append({
                    "artifact": path,
                    "half": side,
                    "ref": ref_name,
                    "arc_score": arc,
                    "note": note,
                })

    # Write JSON artifact
    json_path = os.path.join(outdir, f"halves_rescore_{date_suffix}.json")
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)

    # Write human-readable artifact
    txt_path = os.path.join(outdir, f"halves_rescore_{date_suffix}.txt")
    table_str = format_halves_table(rows)
    with open(txt_path, "w") as f:
        f.write(table_str + "\n")

    print(table_str)
    print(f"\nArtifacts written:")
    print(f"  {json_path}  ({len(rows)} rows)")
    print(f"  {txt_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--halves",
        action="store_true",
        help="Crop L/R halves and score each half vs each ref (man + aria).",
    )
    ap.add_argument(
        "--date",
        default=datetime.date.today().strftime("%Y%m%d"),
        help="Date suffix for output file names (default: today).",
    )
    ap.add_argument(
        "--artifacts",
        nargs="+",
        default=None,
        help="Artifact paths or glob patterns for halves mode "
        "(default: the §7.2 pod-arc set).",
    )
    ap.add_argument(
        "--outdir",
        default="logs",
        help="Output directory for artifact files (default: logs/).",
    )
    args = ap.parse_args()

    v = IdentityValidator()

    if args.halves:
        return run_halves(v, args.outdir, args.date, args.artifacts)

    # Default mode: unchanged original behavior
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
