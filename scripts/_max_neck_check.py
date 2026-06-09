#!/usr/bin/env python3
"""Neck-artifact validation — POSITIVE anatomy phrasing (FLUX max-tier has no negative channel).

Same seed/cfg/base settings as the SUPIR cfg A/B baseline (cfg28_prod, seed 741305880,
arc 0.7939) which showed the recurring neck/collarbone elongation. ONLY the positive prompt
changes: adds explicit anatomy guidance. Compare arc + the saved image against the A/B
baseline logs/max_supir_ab_cfg28_prod_s741305880.jpg to see if positive phrasing mitigates
the artifact (validates the §5.4 recipe's positive-anatomy advice).
"""
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
SEED = 741305880

# Baseline A/B prompt + POSITIVE anatomy guidance appended (no negative channel on FLUX max).
PROMPT = (
    "Photorealistic cinematic close-up portrait of a single woman, solo, looking "
    "directly into the camera with a warm natural expression, head-and-shoulders "
    "framing, shoulder-length hair, soft natural key light, shallow depth of field, "
    "subtle film grain, 85mm lens, ultra-detailed skin texture. One person only. "
    "Natural proportional neck and shoulders, well-defined collarbone, anatomically "
    "correct head-to-neck proportions, relaxed natural posture."
)


def build():
    with open(REF, "rb") as f:
        face_remote = requests.post(
            f"{URL}/upload/image", files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    print(f"uploaded ref -> {face_remote}; classes={len(available)}", flush=True)
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))  # cfg 2.8, hires 0.40, supir on
    q._prune_unavailable(w, available, True, False)
    q._inject_identity(w, None, face_remote, params, True)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = SEED
    return w


def main():
    w = build()
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": w}, timeout=30).json()["prompt_id"]
    print(f"queued {pid}", flush=True)
    for _ in range(110):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"RUN ERROR: {str(st.get('messages'))[:900]}", flush=True); return 1
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print("completed but no images", flush=True); return 1
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = "logs/max_neck_check_anatomy.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            cs = score_candidate(path, REF, threshold=0.6)
            print(f"SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min) "
                  f"arc={cs.arc_score:.4f}", flush=True)
            print("compare vs baseline logs/max_supir_ab_cfg28_prod_s741305880.jpg (arc 0.7939, neck artifact)", flush=True)
            return 0
    print("TIMEOUT", flush=True); return 1


if __name__ == "__main__":
    sys.exit(main())
