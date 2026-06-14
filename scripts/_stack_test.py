#!/usr/bin/env python3
"""Faster identity boost: stack production-lean + Super-Realism LoRA + ReActor.

Strips the painterly max stages (FaceDetailer OFF, Detail-Daemon OFF) and uses
production-style PuLID (1.0, start 0.2 — lets FLUX set a natural base first), but
KEEPS the identity stack that worked: Super-Realism LoRA (realism+id) + ReActor
(in-workflow node 610, the 0.82 lock) + softened SUPIR-A (clean finish on a LoRA
base). Goal: production-leaning realism WITH usable identity (>=0.75) — no training.
2 hair-specified scenes; scores identity.
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

SCENES = [
    ("1_window", 990711,
     "Super Realism, candid cinematic photograph of a woman with dark brown wavy "
     "shoulder-length hair and fair skin, solo, close-up, soft window light, plain "
     "interior wall, natural unretouched skin, 35mm, shallow depth of field. "
     "Photorealistic, one person, plain background."),
    ("2_cinematic", 990722,
     "Super Realism, cinematic film still of a woman with dark brown wavy shoulder-length "
     "hair and fair skin, solo, medium close-up, dramatic warm side light, dark moody "
     "plain background, filmic color, shot on film. Photorealistic, one person, plain "
     "dark background."),
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
        pulid_weight=1.0, pulid_start_at=0.2, pulid_end_at=1.0,  # production-style
        guidance=3.0,
        detail_daemon_amount=0.0,        # OFF (production has none)
        face_detailer_enabled=False,     # OFF (production has none)
        supir_enabled=True,              # softened SUPIR-A: clean finish on LoRA base
        final_resolution=(1920, 1080),
        lora_strength_model=1.0, lora_strength_clip=1.0,
    ))
    q._prune_unavailable(w, _available, True, True, False)
    q._inject_identity(w, LORA, _face_remote, params, True)   # ReActor 610 stays ON
    q._inject_conditioning(w, prompt, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = seed
    return w


def run(wf, name):
    t = time.time()
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        print(f"[{name}] POST REJECT {r.status_code}: {r.text[:800]}", flush=True); return None
    pid = r.json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(110):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception:
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] RUN ERROR: {str(st.get('messages'))[:800]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/stack_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    rows = []
    for name, seed, prompt in SCENES:
        wf = build(prompt, seed)
        print(f"\n[{name}] lean+LoRA+ReActor+SUPIR-A seed={seed}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            rows.append((name, cs.arc_score))
            print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\n=== stack: realism (eyeball) + identity (>=0.75 = usable) ===", flush=True)
    for n, s in rows:
        print(f"  {n}: {s:.3f}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
