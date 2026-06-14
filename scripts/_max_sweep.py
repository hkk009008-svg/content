#!/usr/bin/env python3
"""Realism SWEEP — 9 combinations of the base-generation levers, no SUPIR.

The 'off from real' look lives in the base FLUX+PuLID generation, so this sweeps
the levers that drive it — pulid_weight, FLUX guidance, detail_daemon, FaceDetailer,
pulid_end_at — across 9 diverse combos on ONE seed (clean A/B), ReActor ON (identity),
photoreal prompt, SUPIR OFF (fast; SUPIR isn't the painterly cause and would 5x the
time). Produces a browseable pool; the winning settings then get clean finishing + Veo.
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

SEED = 990001

# (name, {lever overrides}). All: ReActor ON, SUPIR OFF, same seed + prompt.
COMBOS = [
    ("1_base",       dict(pulid_weight=0.85, guidance=3.5, detail_daemon_amount=0.5, face_detailer_enabled=True,  pulid_end_at=0.9)),
    ("2_lowpulid",   dict(pulid_weight=0.50, guidance=3.5, detail_daemon_amount=0.5, face_detailer_enabled=True,  pulid_end_at=0.9)),
    ("3_lowguide",   dict(pulid_weight=0.85, guidance=2.2, detail_daemon_amount=0.3, face_detailer_enabled=True,  pulid_end_at=0.9)),
    ("4_nodetail",   dict(pulid_weight=0.85, guidance=3.5, detail_daemon_amount=0.0, face_detailer_enabled=False, pulid_end_at=0.9)),
    ("5_photorealA", dict(pulid_weight=0.55, guidance=2.5, detail_daemon_amount=0.0, face_detailer_enabled=False, pulid_end_at=0.9)),
    ("6_photorealB", dict(pulid_weight=0.45, guidance=2.0, detail_daemon_amount=0.0, face_detailer_enabled=False, pulid_end_at=0.7)),
    ("7_mid",        dict(pulid_weight=0.70, guidance=3.0, detail_daemon_amount=0.2, face_detailer_enabled=True,  pulid_end_at=0.9)),
    ("8_pulidfade",  dict(pulid_weight=0.85, guidance=3.0, detail_daemon_amount=0.0, face_detailer_enabled=True,  pulid_end_at=0.5)),
    ("9_softid",     dict(pulid_weight=0.60, guidance=2.8, detail_daemon_amount=0.1, face_detailer_enabled=True,  pulid_end_at=0.8)),
]

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


def build(overrides):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    params["supir_enabled"] = False   # base-look sweep; fast
    params.update(overrides)
    q._prune_unavailable(w, _available, True, True, False)
    q._inject_identity(w, None, _face_remote, params, True)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = SEED
    return w


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(80):
        time.sleep(10)
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
                print(f"[{name}] no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/max_sweep_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    for name, ov in COMBOS:
        wf = build(ov)
        print(f"\n[{name}] {ov}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\nDONE — sweep complete; build the grid.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
