"""Diagnostic: is DeepFace/GhostFaceNet's EMBEDDING non-deterministic for a
fixed input image, and what is the resulting identity-score swing?

The 2026-06-13 ⭐#2 instrument debt was attributed to phantom face SELECTION,
but _probe_figure_read_determinism showed selection is stable while the man-ref
embedding is NOT: same detected bbox, two distinct embedding vectors across
runs. This probe quantifies that:
  - distinct embeddings over N runs + their frequency
  - max pairwise cosine DISTANCE between distinct embeddings
  - the man-SCORE swing each distinct ref embedding produces against a fixed
    probe face crop (so the swing is reported in score units, not abstract cos)
  - whether align=False or TF-determinism removes it (TF env tested via a
    separate process; this one compares align True vs False in-process)

Run:
  PYTHONPATH=. .venv/bin/python scripts/_probe_embedding_determinism.py --runs 20
  TF_DETERMINISTIC_OPS=1 TF_NUM_INTEROP_THREADS=1 TF_NUM_INTRAOP_THREADS=1 \
      PYTHONPATH=. .venv/bin/python scripts/_probe_embedding_determinism.py --runs 20 --tag deterministic
"""
import argparse
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

MAN_REF = "logs/p12_fresh_face_man.jpg"
PROBE_FACE = "logs/passb_d_n1.jpg"  # left half holds the man at ~0.870


def emb_md5(e: np.ndarray) -> str:
    return hashlib.md5(np.ascontiguousarray(e, dtype=np.float64).tobytes()).hexdigest()[:8]


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def represent_largest(image_path, align):
    from deepface import DeepFace
    el = DeepFace.represent(
        img_path=image_path, model_name="GhostFaceNet",
        enforce_detection=False, align=align,
    )
    best_area = -1.0
    best = None
    for e in el:
        fa = e.get("facial_area", {})
        w, h = fa.get("w", 0), fa.get("h", 0)
        area = w * h
        # mimic OK gate loosely: ignore obvious whole-image + sub-1%
        if area > best_area:
            best_area = area
            best = np.array(e["embedding"])
    return best


def run_variant(image_path, runs, align, label):
    embs = [represent_largest(image_path, align) for _ in range(runs)]
    md5s = [emb_md5(e) for e in embs]
    distinct = {}
    for m, e in zip(md5s, embs):
        distinct.setdefault(m, {"count": 0, "emb": e})
        distinct[m]["count"] += 1
    keys = list(distinct)
    # max pairwise cosine distance between distinct clusters
    max_dist = 0.0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            d = 1.0 - cos(distinct[keys[i]]["emb"], distinct[keys[j]]["emb"])
            max_dist = max(max_dist, d)
    print(f"[{label}] runs={runs} distinct_embeddings={len(keys)} "
          f"freq={[distinct[k]['count'] for k in keys]} "
          f"max_pairwise_cos_dist={max_dist:.2e}", file=sys.stderr)
    return distinct


def run_load_test(runs, workers, date_suffix, outdir):
    """Force the OpenCV alignment race under induced cv2 load, then show the REAL
    validator guard (_cv2_single_thread) eliminates it. This is the committed
    R-MEASURE instrument for the determinism fix: the quiet-machine race is too
    rare to A/B reliably, so we drive contention with `workers` cv2-hammer
    threads. Compares, under load:
      - UNGUARDED (default cv2 threads): the cold-draw fires (>1 distinct)
      - GUARDED (validator._cv2_single_thread): pinned to 1 distinct
    2026-06-13 macOS/GCD result: unguarded 8/30 diverge, guarded 30/30 identical.
    """
    import json
    import threading
    import cv2
    from deepface import DeepFace
    from identity.validator import _cv2_single_thread, _classify_face_detection

    def largest_ok(path):
        iw, ih = Image.open(path).size
        el = DeepFace.represent(img_path=path, model_name="GhostFaceNet",
                                enforce_detection=False, align=True)
        ba, be = -1.0, None
        for e in el:
            fa = e.get("facial_area", {})
            w, h = fa.get("w", 0), fa.get("h", 0)
            if _classify_face_detection(
                w, h, iw, ih, float(e.get("face_confidence") or 0.0)
            ) == "OK":
                a = float(w * h)
                if a > ba:
                    ba, be = a, np.array(e["embedding"])
        return be

    arr = (np.arange(1024 * 1024, dtype="float32") % 255).reshape(1024, 1024)
    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            cv2.GaussianBlur(arr, (9, 9), 0)
            cv2.resize(arr, (2048, 2048))
            cv2.Sobel(arr, cv2.CV_32F, 1, 0)

    hammers = [threading.Thread(target=hammer, daemon=True) for _ in range(workers)]
    for t in hammers:
        t.start()
    backend = next((ln.strip() for ln in cv2.getBuildInformation().splitlines()
                    if "Parallel" in ln), "unknown")
    default_threads = cv2.getNumThreads()
    unguarded, guarded = {}, {}
    try:
        for _ in range(runs):
            cv2.setNumThreads(default_threads)  # ensure default (racy) each time
            m = emb_md5(largest_ok(MAN_REF))
            unguarded[m] = unguarded.get(m, 0) + 1
        for _ in range(runs):
            with _cv2_single_thread():           # the REAL fix
                m = emb_md5(largest_ok(MAN_REF))
            guarded[m] = guarded.get(m, 0) + 1
    finally:
        stop.set()
        for t in hammers:
            t.join(timeout=1.0)

    report = {
        "cv2_parallel_backend": backend,
        "default_num_threads": default_threads,
        "workers": workers, "runs": runs,
        "unguarded_distinct": len(unguarded), "unguarded_freq": unguarded,
        "guarded_distinct": len(guarded), "guarded_freq": guarded,
        "guard_eliminates_race": len(guarded) == 1 and len(unguarded) > 1,
    }
    print(f"[LOAD] {backend} | default_threads={default_threads} "
          f"| workers={workers} runs={runs}", file=sys.stderr)
    print(f"   UNGUARDED: distinct={len(unguarded)} freq={unguarded}", file=sys.stderr)
    print(f"   GUARDED  : distinct={len(guarded)} freq={guarded}", file=sys.stderr)
    print(f"   => guard_eliminates_race={report['guard_eliminates_race']} "
          f"(False on a quiet machine if the race never fired unguarded)",
          file=sys.stderr)
    out = os.path.join(outdir, f"embedding_determinism_load_{date_suffix}.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--tag", default="default")
    ap.add_argument("--load", action="store_true",
                    help="Induced-load A/B: unguarded vs the real _cv2_single_thread guard.")
    ap.add_argument("--workers", type=int, default=6, help="cv2-hammer threads for --load.")
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--outdir", default="logs")
    args = ap.parse_args()

    if args.load:
        return run_load_test(args.runs, args.workers, args.date, args.outdir)

    print(f"=== tag={args.tag}  "
          f"TF_DETERMINISTIC_OPS={os.environ.get('TF_DETERMINISTIC_OPS')} "
          f"INTRA={os.environ.get('TF_NUM_INTRAOP_THREADS')} ===", file=sys.stderr)

    print("--- MAN_REF, align=True ---", file=sys.stderr)
    ref_clusters = run_variant(MAN_REF, args.runs, True, "MAN_REF align=True")
    print("--- MAN_REF, align=False ---", file=sys.stderr)
    run_variant(MAN_REF, args.runs, False, "MAN_REF align=False")

    # Score impact: fixed probe face (computed once, align=True majority) vs each
    # distinct ref cluster -> the man-score swing the ref non-determinism causes.
    probe = represent_largest(PROBE_FACE, True)
    print("--- man-score (probe face vs each distinct ref cluster) ---", file=sys.stderr)
    scores = []
    for k, v in ref_clusters.items():
        s = (1.0 + cos(probe, v["emb"])) / 2.0
        scores.append(s)
        print(f"   ref {k} (x{v['count']}): man_score={s:.4f}", file=sys.stderr)
    if scores:
        print(f"   => SCORE SWING from ref non-determinism: "
              f"{max(scores) - min(scores):.4f} "
              f"(min {min(scores):.4f}  max {max(scores):.4f})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
