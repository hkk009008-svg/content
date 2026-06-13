"""Diagnostic probe: is figure-read selection non-deterministic, and WHY?

Root-cause instrument for the binding-metric non-determinism (man read
0.637/0.683/0.805 across warm invocations of the same over-cooked render,
±0.17 — operator handoff 2026-06-13 ⭐#2). Runs DeepFace.represent N times on
each half-crop of the given artifacts and records, per run, EVERY detection's
(x, y, w, h, area, area_pct, confidence, class) plus the largest-OK selection
and its resulting cosine score vs a reference embedding.

It distinguishes three mechanisms the fix must handle differently:
  - ORDER variance   : same bbox SET each run, different RETURN ORDER + an area
                       tie => first-wins selection flips. Fix = total ordering.
  - SET variance     : the detector returns DIFFERENT bboxes run-to-run =>
                       represent() itself is non-deterministic. Fix = make
                       selection robust to the junk (confidence floor) so only
                       the one stable real face can ever be selected.
  - CONF separation  : do phantom (texture-patch) detections sit at a lower
                       face_confidence than the real figure? If so a confidence
                       floor cleanly prunes them. This is the number we need to
                       SET any threshold empirically rather than by guess.

Run:
  PYTHONPATH=. .venv/bin/python scripts/_probe_figure_read_determinism.py \
      --artifacts logs/passb_q_n1.jpg logs/passb_d_n1.jpg --runs 6

Writes logs/figure_read_determinism_<date>.json (+ a stderr summary).
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from identity.validator import _classify_face_detection
from scripts._face_reads import ref_embedding_largest_ok

MAN_REF = "logs/p12_fresh_face_man.jpg"


def crop_half(img_path: str, side: str, outdir: str) -> str:
    img = Image.open(img_path)
    w, h = img.size
    box = (0, 0, w // 2, h) if side == "left" else (w // 2, 0, w, h)
    out = os.path.join(
        outdir, f"{os.path.splitext(os.path.basename(img_path))[0]}_{side}.jpg"
    )
    img.crop(box).save(out, quality=95)
    return out


def represent_detections(image_path: str):
    """Return the raw DeepFace detections as a list of dicts (one run)."""
    from deepface import DeepFace

    img_w, img_h = Image.open(image_path).size
    img_area = img_w * img_h
    emb_list = DeepFace.represent(
        img_path=image_path, model_name="GhostFaceNet", enforce_detection=False
    )
    dets = []
    for i, entry in enumerate(emb_list):
        fa = entry.get("facial_area", {})
        x, y = fa.get("x", 0), fa.get("y", 0)
        w, h = fa.get("w", 0), fa.get("h", 0)
        conf = float(entry.get("face_confidence") or 0.0)
        cls = _classify_face_detection(w, h, img_w, img_h, conf)
        area = float(w * h)
        dets.append({
            "order": i,
            "x": x, "y": y, "w": w, "h": h,
            "area": area,
            "area_pct": 100.0 * area / img_area if img_area else 0.0,
            "conf": conf,
            "class": cls,
            "emb": np.array(entry["embedding"]),
        })
    return dets, img_area


def select_largest_ok(dets):
    """Current selection rule: first detection at the max OK area wins."""
    best_area = -1.0
    best = None
    for d in dets:
        if d["class"] == "OK" and d["area"] > best_area:
            best_area = d["area"]
            best = d
    return best


def cos_score(emb, ref):
    cs = float(np.dot(emb, ref) / (np.linalg.norm(emb) * np.linalg.norm(ref) + 1e-10))
    return (1.0 + cs) / 2.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", nargs="+", required=True)
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--sides", nargs="+", default=["left", "right"])
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--outdir", default="logs")
    args = ap.parse_args()

    crop_dir = os.path.join(args.outdir, "halves_crops")
    os.makedirs(crop_dir, exist_ok=True)

    print("Computing man ref embedding (largest OK)...", file=sys.stderr)
    ref = ref_embedding_largest_ok(MAN_REF, "man")

    report = []
    for art in args.artifacts:
        if not os.path.exists(art):
            print(f"SKIP missing {art}", file=sys.stderr)
            continue
        for side in args.sides:
            crop = crop_half(art, side, crop_dir)
            run_records = []
            scores = []
            det_signatures = set()
            order_signatures = set()
            for r in range(args.runs):
                dets, img_area = represent_detections(crop)
                # set signature: sorted bbox tuples (order-independent)
                sig = tuple(sorted((d["x"], d["y"], d["w"], d["h"]) for d in dets))
                det_signatures.add(sig)
                # order signature: bbox tuples in returned order
                order_signatures.add(tuple((d["x"], d["y"], d["w"], d["h"]) for d in dets))
                sel = select_largest_ok(dets)
                score = cos_score(sel["emb"], ref) if sel is not None else None
                if score is not None:
                    scores.append(score)
                run_records.append({
                    "run": r,
                    "n_det": len(dets),
                    "classes": {c: sum(1 for d in dets if d["class"] == c)
                                for c in ("OK", "TINY", "DEGENERATE")},
                    "selected": None if sel is None else {
                        "x": sel["x"], "y": sel["y"], "w": sel["w"], "h": sel["h"],
                        "area_pct": round(sel["area_pct"], 3),
                        "conf": round(sel["conf"], 4),
                    },
                    "score": None if score is None else round(score, 4),
                    "detections": [
                        {k: (round(d[k], 4) if isinstance(d[k], float) else d[k])
                         for k in ("order", "x", "y", "w", "h", "area_pct", "conf", "class")}
                        for d in dets
                    ],
                })
            sc_arr = np.array(scores) if scores else np.array([])
            summary = {
                "artifact": art,
                "side": side,
                "runs": args.runs,
                "score_min": round(float(sc_arr.min()), 4) if scores else None,
                "score_max": round(float(sc_arr.max()), 4) if scores else None,
                "score_spread": round(float(sc_arr.max() - sc_arr.min()), 4) if scores else None,
                "n_distinct_scores": len(set(round(s, 4) for s in scores)),
                "n_none_reads": args.runs - len(scores),
                "set_varies": len(det_signatures) > 1,
                "order_varies": len(order_signatures) > 1,
                "n_distinct_sets": len(det_signatures),
                "n_distinct_orders": len(order_signatures),
                "runs_detail": run_records,
            }
            report.append(summary)
            print(
                f"[{art} {side}] spread={summary['score_spread']} "
                f"distinct_scores={summary['n_distinct_scores']} "
                f"none_reads={summary['n_none_reads']} "
                f"set_varies={summary['set_varies']} order_varies={summary['order_varies']}",
                file=sys.stderr,
            )

    out = os.path.join(args.outdir, f"figure_read_determinism_{args.date}.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
