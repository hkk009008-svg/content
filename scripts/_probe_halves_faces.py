"""Per-face diagnostic for halves-mode arc scores — which detection supplied each cell.

`_arc_score_session.py --halves` reports max-over-detections per (half, ref)
cell (validator best-face semantics). On the 2026-06-12 reconciliation probe
that max was frequently supplied by NON-FIGURE detections: tiny texture
patches (<1% of crop area) and whole-image fallback boxes emitted by
`DeepFace.represent(..., enforce_detection=False)` when no face is found.
This instrument enumerates EVERY detection per crop — bbox, area ratio,
confidence, (1+cos)/2 vs each ref, mirroring IdentityValidator arithmetic
exactly — and classifies each as OK / TINY / DEGENERATE, so a halves-table
cell can be traced to the face (or junk) that produced it.

Run: PYTHONPATH=. .venv/bin/python scripts/_probe_halves_faces.py
Emits logs/halves_faces_probe_YYYYMMDD.json + .txt (gitignored, local).
"""
import argparse
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Canonical refs — same as scripts/_arc_score_session.py
DEFAULT_REFS = {
    "man": "logs/p12_fresh_face_man.jpg",
    "aria": "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg",
}
DEFAULT_CROPS = ["logs/halves_crops/*.jpg"]

TINY_AREA_RATIO = 0.01  # below this fraction of the crop, a detection is junk
DEGENERATE_MARGIN_PX = 2  # bbox within this of full crop size = fallback box


def classify_detection(
    bbox_w: int, bbox_h: int, img_w: int, img_h: int, confidence: float
) -> str:
    """Classify one detection: DEGENERATE (whole-image fallback), TINY, or OK.

    DEGENERATE: bbox spans the whole crop (enforce_detection=False emits this
    when no face is found; confidence is typically 0.0) — an embedding of the
    entire half-image, not a face.
    TINY: bbox under TINY_AREA_RATIO of the crop — texture patches at 50-95px
    scored 0.59-0.78 vs the man ref on 2026-06-12 while true figures read
    0.47-0.52, so these routinely steal the best-face max.
    """
    if bbox_w >= img_w - DEGENERATE_MARGIN_PX and bbox_h >= img_h - DEGENERATE_MARGIN_PX:
        return "DEGENERATE"
    if img_w and img_h and (bbox_w * bbox_h) / (img_w * img_h) < TINY_AREA_RATIO:
        return "TINY"
    return "OK"


def format_probe_table(rows: list[dict]) -> str:
    """Human-readable table; one line per detection."""
    header = (
        f"{'crop':52s} {'i':>2s} {'bbox':>22s} {'area%':>6s} "
        f"{'conf':>5s} {'man':>6s} {'aria':>6s} {'class':10s}"
    )
    lines = [
        "=== HALVES PER-FACE PROBE (every detection; validator arithmetic) ===",
        header,
        "-" * len(header),
    ]
    for r in rows:
        bbox = f"({r['x']},{r['y']},{r['w']}x{r['h']})"
        lines.append(
            f"{r['crop']:52s} {r['face_index']:>2d} {bbox:>22s} "
            f"{r['area_pct']:>6.2f} {r['confidence']:>5.2f} "
            f"{r['man']:>6.3f} {r['aria']:>6.3f} {r['classification']:10s}"
        )
    return "\n".join(lines)


def run_probe(crop_patterns, refs, outdir, date_suffix) -> int:
    import numpy as np
    from PIL import Image
    from deepface import DeepFace

    ref_embs = {}
    for name, path in refs.items():
        el = DeepFace.represent(
            img_path=path, model_name="GhostFaceNet", enforce_detection=False
        )
        # validator _get_embedding contract: el[0]
        ref_embs[name] = np.array(el[0]["embedding"])
        print(f"REF {name}: {len(el)} detection(s); using [0]")

    crops = [p for pat in crop_patterns for p in (sorted(glob.glob(pat)) or [pat])]
    rows = []
    for crop in crops:
        img = Image.open(crop)
        img_w, img_h = img.size
        el = DeepFace.represent(
            img_path=crop, model_name="GhostFaceNet", enforce_detection=False
        )
        for i, e in enumerate(el):
            emb = np.array(e["embedding"])
            fa = e.get("facial_area", {})
            w, h = fa.get("w", 0), fa.get("h", 0)
            row = {
                "crop": os.path.basename(crop),
                "face_index": i,
                "x": fa.get("x", 0), "y": fa.get("y", 0), "w": w, "h": h,
                "area_pct": 100.0 * w * h / (img_w * img_h) if img_w and img_h else 0.0,
                "confidence": float(e.get("face_confidence") or 0.0),
                "classification": classify_detection(
                    w, h, img_w, img_h, float(e.get("face_confidence") or 0.0)
                ),
            }
            for name, ref in ref_embs.items():
                cos = float(np.dot(emb, ref) / (
                    np.linalg.norm(emb) * np.linalg.norm(ref) + 1e-10
                ))
                row[name] = (1 + cos) / 2  # validator similarity normalization
            rows.append(row)

    os.makedirs(outdir, exist_ok=True)
    json_path = os.path.join(outdir, f"halves_faces_probe_{date_suffix}.json")
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)
    txt_path = os.path.join(outdir, f"halves_faces_probe_{date_suffix}.txt")
    table = format_probe_table(rows)
    with open(txt_path, "w") as f:
        f.write(table + "\n")
    print(table)
    print(f"\nArtifacts written:\n  {json_path}  ({len(rows)} rows)\n  {txt_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--crops", nargs="+", default=None,
        help="Crop paths or glob patterns (default: logs/halves_crops/*.jpg).",
    )
    ap.add_argument(
        "--ref", action="append", default=None, metavar="NAME=PATH",
        help="Reference as name=path; repeatable (default: canonical man + aria).",
    )
    ap.add_argument("--outdir", default="logs")
    ap.add_argument(
        "--date", default=datetime.date.today().strftime("%Y%m%d"),
        help="Date suffix for output file names (default: today).",
    )
    args = ap.parse_args()

    refs = (
        dict(r.split("=", 1) for r in args.ref) if args.ref else dict(DEFAULT_REFS)
    )
    return run_probe(args.crops or DEFAULT_CROPS, refs, args.outdir, args.date)


if __name__ == "__main__":
    raise SystemExit(main())
