#!/usr/bin/env python3
"""SUPIR cfg CLEAN A/B — production 2.8 vs candidate 2.0, isolate ONLY supir_cfg_scale.

The pod sweep that produced the 2026-06-09 handoff compared SUPIR cfg 2.0 (arc 0.851)
vs a cfg-4.0 baseline (arc 0.831) — but production MAX_QUALITY_TEMPLATES already ship
2.8, and 2.0-vs-2.8 was never measured. This settles that: same seed, same prompt, the
REAL production injection (get_max_quality_params + quality_max helpers), SUPIR ON, and
ONLY node-502 cfg_scale_start/end varied between 2.8 and 2.0 (via params['supir_cfg_scale']
-> _inject_post_passes, NOT a manual node patch). restore_cfg/steps/churn stay at the
production defaults for BOTH variants, unlike scripts/_max_supir_tune.py which confounds
4 params. Identity scored with the same face_validator_gate.score_candidate the harness
uses. Images saved for visual (over-processing / realism) inspection.

URL is read from settings (COMFYUI_SERVER_URL in .env) so a restarted pod is a one-line
.env change, not an edit here. Usage:  python scripts/_max_supir_cfg_ab.py [seed ...]
Default seed 741305880 (the handoff's SUPIR-sweep seed). Each gen ~8-9 min (SUPIR+hires).
"""
import copy
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quality_max as q
from workflow_selector import get_max_quality_params
from face_validator_gate import score_candidate
from config.settings import get_settings

URL = get_settings().comfyui_server_url.rstrip("/")
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
os.environ.setdefault("MAX_MODEL_PRECISION", "fp16")

PROMPT = (
    "Photorealistic cinematic close-up portrait of a single woman, solo, looking "
    "directly into the camera with a warm natural expression, head-and-shoulders "
    "framing, shoulder-length hair, soft natural key light, shallow depth of field, "
    "subtle film grain, 85mm lens, ultra-detailed skin texture. One person only."
)

# ONLY supir_cfg_scale differs. Everything else = production portrait template.
VARIANTS = {"cfg28_prod": 2.8, "cfg20_cand": 2.0}

_face_remote = None
_available = None


def _setup():
    global _face_remote, _available
    print(f"pod URL = {URL}", flush=True)
    with open(REF, "rb") as f:
        _face_remote = requests.post(
            f"{URL}/upload/image", files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    _available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    print(f"uploaded face ref -> {_face_remote}; pod classes={len(_available)}", flush=True)
    if "SUPIR_sample" not in _available:
        print("FATAL: SUPIR_sample not on pod — cannot run SUPIR cfg A/B.", flush=True)
        sys.exit(2)


def build(supir_cfg, seed):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    params["supir_enabled"] = True            # we ARE testing SUPIR
    params["supir_cfg_scale"] = supir_cfg     # the ONLY lever that varies
    q._prune_unavailable(w, _available, True, True, False)
    q._inject_identity(w, None, _face_remote, params, True)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = seed
    if "502" not in w:
        print("FATAL: node 502 absent after build — SUPIR pruned?", flush=True)
        sys.exit(2)
    n = w["502"]["inputs"]
    print(f"   node 502: cfg_start={n.get('cfg_scale_start')} cfg_end={n.get('cfg_scale_end')} "
          f"restore_cfg={n.get('restore_cfg')} steps={n.get('steps')}", flush=True)
    return w


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for _ in range(110):  # ~22 min ceiling
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] RUN ERROR: {str(st.get('messages'))[:900]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print(f"[{name}] completed but no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/max_supir_ab_{name}.jpg"
            os.makedirs("logs", exist_ok=True)
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, "
                  f"{(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    seeds = [int(s) for s in sys.argv[1:]] or [741305880]
    _setup()
    results = []
    for seed in seeds:
        print(f"\n===== seed {seed} =====", flush=True)
        for name, cfg in VARIANTS.items():
            tag = f"{name}_s{seed}"
            print(f"\n[{tag}] building SUPIR cfg={cfg}", flush=True)
            wf = build(cfg, seed)
            path = run(wf, tag)
            if path:
                cs = score_candidate(path, REF, threshold=0.6)
                print(f"[{tag}] identity arc={cs.arc_score:.4f}", flush=True)
                results.append((tag, cfg, seed, cs.arc_score, path))
    print("\n===== SUMMARY (arc by cfg) =====", flush=True)
    for tag, cfg, seed, arc, path in results:
        print(f"  cfg {cfg}  seed {seed}  arc {arc:.4f}  {path}", flush=True)
    # per-seed delta
    by_seed = {}
    for _, cfg, seed, arc, _ in results:
        by_seed.setdefault(seed, {})[cfg] = arc
    for seed, d in by_seed.items():
        if 2.8 in d and 2.0 in d:
            print(f"  seed {seed}: arc(2.0) - arc(2.8) = {d[2.0]-d[2.8]:+.4f} "
                  f"({'2.0 better' if d[2.0] > d[2.8] else '2.8 better'})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
