"""Task-4 pod acceptance gate for the production PuLID SDXL->FLUX fix (plan
docs/superpowers/plans/2026-06-13-production-pulid-flux-fix.md Chunk 2 / ADR-024).

Controlled A/B on the SAME prompt + seed + aria reference, direct pod /prompt
submits of the production graph (NOT a generate_ai_broll pipeline call):

  OFF (baseline) = production pulid.json with PuLID BYPASSED — pop nodes
                   93/97/99/100/101 and rewire PAG 301.model -> ['112',0] so the
                   sampler gets the raw FLUX UNet (plain FLUX txt2img, no lock).
  ON  (fixed)    = production pulid.json AS-SHIPPED — ApplyPulidFlux face-lock,
                   aria ref on node 93, start_at=0.0.

Both legs reuse _max_passBa_masked_pulid.render_leg (money-path-safe: a rejected
graph returns no prompt_id => $0; timeouts on every paid call). Each FULL artifact
is arc-scored vs the aria reference with the COMMITTED deterministic instrument
(scripts._face_reads.figure_read_score + ref_embedding_largest_ok, post-d48b58b
cv2 single-thread) — full frame, not --halves (single centered face). Scores + md5s
land in logs/prod_pulid_acceptance_<date>.json (R-MEASURE).

GO (plan Task-4 Step 4): ON arc rises materially over OFF AND a face is detected on
ON (read_type != none => FaceDetailer-free binding) AND visually photoreal. Target
toward ~0.87 for a single clean face; primary GO also needs the VISUAL check.

Run: PYTHONPATH=. .venv/bin/python scripts/_prod_pulid_acceptance.py
Pod must be RUNNING + ComfyUI UP.
"""
import copy
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _max_s2_dual_pulid as s2
from _max_passBa_masked_pulid import render_leg

PROMPT = ("a woman with short dark wavy hair, photorealistic cinematic portrait, "
          "soft natural light, medium close-up, detailed skin texture, sharp focus")
PULID_NODES = ("93", "97", "99", "100", "101")


def build_on(aria_remote):
    """Production pulid.json AS-SHIPPED with the aria ref + single-subject prompt."""
    w = json.load(open("pulid.json"))
    w.pop("_metadata", None)
    w["93"]["inputs"]["image"] = aria_remote
    w["122"]["inputs"]["text"] = PROMPT
    assert w["100"]["class_type"] == "ApplyPulidFlux", "ON: node 100 not ApplyPulidFlux"
    assert w["100"]["inputs"]["start_at"] == 0.0, "ON: node 100 start_at != 0.0"
    assert w["301"]["inputs"]["model"] == ["100", 0], "ON: PAG 301 not fed by PuLID 100"
    return w


def build_off():
    """Production pulid.json with the PuLID subgraph removed (plain FLUX txt2img)."""
    w = json.load(open("pulid.json"))
    w.pop("_metadata", None)
    w["122"]["inputs"]["text"] = PROMPT
    w["301"]["inputs"]["model"] = ["112", 0]  # PAG reads the raw FLUX UNet
    for nid in PULID_NODES:
        w.pop(nid, None)
    assert "100" not in w, "OFF: node 100 still present"
    assert w["301"]["inputs"]["model"] == ["112", 0], "OFF: PAG not rewired to raw UNet"
    for nid, node in w.items():
        if not isinstance(node, dict):
            continue
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in set(PULID_NODES):
                raise SystemExit(f"OFF: dangling ref {nid}.{k} -> {v} (popped PuLID node)")
    return w


def _md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()[:12]


def _score(path, ref_emb):
    from scripts._face_reads import figure_read_score
    r = figure_read_score(path, ref_emb, ref_name="aria")
    return {"path": path, "md5": _md5(path), "arc": r["score"],
            "read_type": r["read_type"], "n_det": r["n_detections"],
            "area_pct": r["face_area_pct"]}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1,
                    help="ON-leg seed count (1=A/B acceptance, 4=seed robustness)")
    ap.add_argument("--dry", action="store_true",
                    help="$0 structural build + asserts only (no upload, no render)")
    args = ap.parse_args()
    if args.n > len(s2.SEEDS):
        raise SystemExit(f"--n {args.n} exceeds available seeds {len(s2.SEEDS)}")

    seed = s2.SEEDS[0]
    if args.dry:
        off = build_off()
        on = build_on("dry_ref.jpg")
        print(f"DRY OK | seed={seed}", flush=True)
        print(f"  OFF: 100-present={'100' in off} 301.model={off['301']['inputs']['model']} "
              f"nodes={len(off)} (popped {PULID_NODES})", flush=True)
        print(f"  ON : 100={on['100']['class_type']} start_at={on['100']['inputs']['start_at']} "
              f"301.model={on['301']['inputs']['model']} 93.image={on['93']['inputs']['image']} "
              f"nodes={len(on)}", flush=True)
        print(f"  save node 9 <- {off['9']['inputs']['images']} (both legs); seed node 25 present: "
              f"{'25' in off and '25' in on}", flush=True)
        if not os.path.exists(s2.ARIA_REF):
            print(f"  WARN aria ref missing: {s2.ARIA_REF}", flush=True)
        else:
            print(f"  aria ref OK: {s2.ARIA_REF}", flush=True)
        return 0

    seeds = s2.SEEDS[:args.n]
    aria_remote = s2._upload(s2.ARIA_REF, "prodacc_aria.jpg")
    print(f"uploaded aria ref -> {aria_remote}; seeds={seeds}", flush=True)

    off = build_off()
    print(f"OFF graph built (PuLID bypassed) — rendering baseline (seed {seeds[0]})...", flush=True)
    saved_off, peak_off, rc_off = render_leg(off, [seeds[0]], 1, save_prefix="logs/prod_pulid_off_n")
    if rc_off != 0 or not saved_off:
        raise SystemExit(f"OFF render FAILED rc={rc_off}")

    on = build_on(aria_remote)
    print(f"ON graph built (ApplyPulidFlux face-lock) — rendering N={args.n}...", flush=True)
    saved_on, peak_on, rc_on = render_leg(on, seeds, args.n, save_prefix="logs/prod_pulid_on_n")
    if rc_on != 0 or len(saved_on) < args.n:
        raise SystemExit(f"ON render FAILED rc={rc_on} ({len(saved_on)}/{args.n})")

    print("scoring (deterministic, committed instrument)...", flush=True)
    from scripts._face_reads import ref_embedding_largest_ok
    ref_emb = ref_embedding_largest_ok(s2.ARIA_REF, "aria")
    off_res = _score(saved_off[0], ref_emb)
    on_res = [dict(_score(p, ref_emb), seed=seeds[i]) for i, p in enumerate(saved_on)]

    result = {
        "task": "prod-pulid-flux acceptance (Task-4, plan Chunk 2)",
        "graph": "pulid.json", "n": args.n, "seeds": seeds, "prompt": PROMPT, "ref": s2.ARIA_REF,
        "peak_vram_gib": round(max(peak_off, peak_on), 1),
        "off": off_res, "on": on_res,
    }
    date = datetime.date.today().strftime("%Y%m%d")
    out = f"logs/prod_pulid_acceptance_{date}.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2), flush=True)

    a_off = off_res["arc"]
    on_arcs = [r["arc"] for r in on_res if r["arc"] is not None]
    faces_on = sum(1 for r in on_res if r["read_type"] != "none")
    bind_ok = sum(1 for r in on_res if r["arc"] is not None and r["arc"] >= 0.75
                  and (a_off is None or r["arc"] > a_off))
    print(f"\n=== TASK-4 ACCEPTANCE READ (N={args.n}) ===", flush=True)
    print(f"OFF (no PuLID, seed {seeds[0]}): arc={a_off if a_off is not None else 'NO_FACE'} [{off_res['read_type']}]", flush=True)
    for r in on_res:
        print(f"ON seed {r['seed']}: arc={r['arc'] if r['arc'] is not None else 'NO_FACE'} "
              f"[{r['read_type']}, area {r['area_pct']:.0f}%]", flush=True)
    if on_arcs:
        print(f"ON arc: mean={sum(on_arcs)/len(on_arcs):.3f} min={min(on_arcs):.3f} max={max(on_arcs):.3f}", flush=True)
    print(f"bind_ok (arc>=0.75 AND >OFF): {bind_ok}/{args.n}; faces detected: {faces_on}/{args.n}", flush=True)
    need = (args.n * 3 + 3) // 4  # ceil(0.75 * n)
    if bind_ok == args.n and faces_on == args.n:
        print("PROVISIONAL: ALL seeds bind >=0.75 over OFF + face on all -> ROBUST GO (confirm VISUAL).", flush=True)
    elif bind_ok >= need:
        print(f"PROVISIONAL: {bind_ok}/{args.n} seeds bind -> majority GO (review misses + VISUAL).", flush=True)
    else:
        print(f"PROVISIONAL: only {bind_ok}/{args.n} bind -> investigate (fp8? NO_FACE? seed-fragile?).", flush=True)
    print(f"recorded -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
