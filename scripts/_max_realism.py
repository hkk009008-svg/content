#!/usr/bin/env python3
"""Realism push — ReActor OFF + candid-photo prompt, SUPIR-A vs SUPIR-off.

The polished v1 read 'off from real' (painterly/CGI sheen) + a neck seam. Two
suspected realism killers: ReActor(610) face-swap seam, and SUPIR's restoration
look. This disables ReActor everywhere (PuLID carries identity) and compares
SUPIR-A (softened) vs SUPIR-off on the SAME seeds, with a strong photoreal
prompt + plain backdrop (RAI-safe). Scores + saves all 4 for a realism pick.

Validates the SUPIR-off graph (no GPU spend) before the real runs.
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

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
os.environ.setdefault("MAX_MODEL_PRECISION", "fp16")

PROMPT = (
    "Candid documentary photograph of a real woman, solo, alone, looking directly "
    "at the camera, natural unretouched skin showing pores and fine texture, minimal "
    "makeup, soft overcast daylight, head and shoulders, shoulder-length wavy brown "
    "hair, plain dark crew-neck t-shirt, plain neutral grey seamless backdrop, shot "
    "on a 35mm camera, photojournalistic, authentic, subtle film grain, shallow depth "
    "of field. Solo studio portrait, no other people, plain empty background. "
    "Hyperrealistic photograph, not a render, not CGI, not airbrushed, not illustration."
)

SEEDS = [880011, 880022]
# (name, supir_on); ReActor is OFF in all.
VARIANTS = [("supirA", True), ("supiroff", False)]

_face_remote = None
_available = None


def _setup():
    global _face_remote, _available
    with open(REF, "rb") as f:
        _face_remote = requests.post(
            f"{URL}/upload/image", files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    _available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    print(f"uploaded face ref -> {_face_remote}; pod classes={len(_available)}", flush=True)


def build(supir_on, seed):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    params["supir_enabled"] = supir_on
    q._prune_unavailable(w, _available, True, False)
    q._inject_identity(w, None, _face_remote, params, True)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    # ReActor OFF (passthrough) — kill the face-swap neck seam; PuLID holds identity.
    if "610" in w:
        w["610"]["inputs"]["enabled"] = False
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = seed
    return w


def validate(wf, name):
    """POST validate-only: 200 => graph valid (interrupt+clear, no spend); 400 => node_errors."""
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code == 200:
        pid = r.json().get("prompt_id")
        requests.post(f"{URL}/interrupt", timeout=10)
        requests.post(f"{URL}/queue", json={"clear": True}, timeout=10)
        print(f"[validate {name}] OK (200, valid graph) — interrupted, no spend", flush=True)
        return True
    print(f"[validate {name}] REJECT {r.status_code}: {r.text[:1200]}", flush=True)
    return False


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(95):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] RUN ERROR: {str(st.get('messages'))[:1000]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print(f"[{name}] no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/max_real_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    # De-risk the SUPIR-off graph before any spend.
    if not validate(build(False, SEEDS[0]), "supiroff-graph"):
        print("ABORT: SUPIR-off graph invalid; not spending.", flush=True)
        return 2
    for seed in SEEDS:
        for vname, supir_on in VARIANTS:
            name = f"{seed}_{vname}"
            wf = build(supir_on, seed)
            print(f"\n[{name}] reactor=OFF supir={'A(2.8/40)' if supir_on else 'OFF'} seed={seed}", flush=True)
            path = run(wf, name)
            if path:
                cs = score_candidate(path, REF, threshold=0.6)
                print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\nDONE — compare logs/max_real_*.jpg (realism + identity)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
