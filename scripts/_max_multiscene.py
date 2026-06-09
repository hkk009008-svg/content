#!/usr/bin/env python3
"""Multi-scene photoreal test with identity-drift control.

Combines everything learned: Super-Realism LoRA (photoreal + identity) + softened
SUPIR-A (clean finish that doesn't re-paint a photoreal base) + STRONG identity
lock (PuLID 0.85 + ReActor face-swap + the SAME reference every scene) to kill the
cross-scene drift that hurt yesterday's production-tier cinema. Lighter detail/
guidance (production-leaning realism). 4 varied cinematic scenes, same character.
Scores each keyframe's identity vs the ref so drift is measurable (want all ~0.8+).
"""
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
LORA = "super-realism.safetensors"

# Per-scene: varied cinematic lighting/composition, SAME character, plain-ish
# backgrounds (Veo RAI-safety). "Super Realism" = LoRA trigger.
SCENES = [
    ("1_window", 770311,
     "Super Realism, candid photograph of a woman, solo alone, close-up, looking at the "
     "camera, soft window light from the side, plain interior wall background, natural "
     "unretouched skin with pores, photojournalistic, 35mm, shallow depth of field. "
     "One person only, plain background, no other people."),
    ("2_cinematic", 770322,
     "Super Realism, cinematic film still of a woman, solo alone, medium close-up, "
     "dramatic warm side light, dark moody plain background, natural skin texture, shot "
     "on film, shallow depth of field, filmic color. One person only, plain dark "
     "background, no other people."),
    ("3_golden", 770333,
     "Super Realism, candid photograph of a woman, solo alone, close-up, warm golden "
     "hour light on the face, soft blurred plain background, natural skin, 85mm, gentle "
     "bokeh, authentic. One person only, plain background, no other people."),
    ("4_studio", 770344,
     "Super Realism, professional photograph of a woman, solo alone, three-quarter "
     "portrait, soft overcast daylight, plain neutral grey seamless studio backdrop, "
     "natural unretouched skin, 50mm, shallow depth of field. One person only, plain "
     "background, no other people."),
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
    print(f"uploaded face ref -> {_face_remote}", flush=True)


def build(prompt, seed):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    params.update(dict(
        pulid_weight=0.85,            # strong identity lock (anti-drift)
        guidance=3.0,                 # slightly lighter
        detail_daemon_amount=0.2,     # less "illustrated"
        face_detailer_enabled=True,
        supir_enabled=True,           # softened SUPIR-A (baked) cleans the LoRA base
        final_resolution=(1920, 1080),
        lora_strength_model=1.0,
        lora_strength_clip=1.0,
    ))
    q._prune_unavailable(w, _available, True, False)
    q._inject_identity(w, LORA, _face_remote, params, True)   # ReActor stays ON (anti-drift)
    q._inject_conditioning(w, prompt, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    # ReActor OFF — Super-Realism LoRA now carries identity; this removes the
    # face-swap neck seam. Drift check proves whether identity still holds.
    if "610" in w:
        w["610"]["inputs"]["enabled"] = False
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = seed
    return w


def run(wf, name):
    t = time.time()
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        print(f"[{name}] POST REJECT {r.status_code}: {r.text[:900]}", flush=True); return None
    pid = r.json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(110):
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
                print(f"[{name}] no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/max_scene_nr_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    scores = []
    for name, seed, prompt in SCENES:
        wf = build(prompt, seed)
        print(f"\n[{name}] seed={seed}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            scores.append((name, cs.arc_score))
            print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\n=== identity across scenes (drift check) ===", flush=True)
    for n, s in scores:
        print(f"  {n}: {s:.3f}", flush=True)
    if scores:
        vals = [s for _, s in scores]
        print(f"  range {min(vals):.3f}-{max(vals):.3f} (tight range = low drift)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
