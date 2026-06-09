#!/usr/bin/env python3
"""Realism LoRA test — #1-base settings + a FLUX realism LoRA on node 700.

The reference is already photoreal but the pipeline renders painterly; a realism
LoRA pushes FLUX's generation aesthetic back toward photographic. Uses the user's
preferred #1-base levers + SAME seed (990001) as sweep #1, so each variant isolates
the LoRA effect vs the no-LoRA baseline (logs/max_sweep_1_base.jpg). No-SUPIR (fast).
LoRA injects via char_lora -> node 700 LoraLoader on the FLUX UNet (PuLID applies on top).
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

SEED = 990001  # == sweep #1, for direct comparison
BASE = dict(pulid_weight=0.85, guidance=3.5, detail_daemon_amount=0.5,
            face_detailer_enabled=True, pulid_end_at=0.9, supir_enabled=False)

COMBOS = [
    ("xlabs_s100", dict(lora="flux_realism_lora.safetensors", sm=1.0, sc=1.0, prefix="")),
    ("super_s080", dict(lora="super-realism.safetensors",     sm=0.8, sc=0.8, prefix="Super Realism, ")),
    ("super_s100", dict(lora="super-realism.safetensors",     sm=1.0, sc=1.0, prefix="Super Realism, ")),
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


def build(combo):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    params.update(BASE)
    params["lora_strength_model"] = combo["sm"]
    params["lora_strength_clip"] = combo["sc"]
    q._prune_unavailable(w, _available, True, False)
    # char_lora set -> _inject_identity keeps node 700 LoraLoader + loads this LoRA
    q._inject_identity(w, combo["lora"], _face_remote, params, True)
    q._inject_conditioning(w, combo["prefix"] + PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = SEED
    if "700" not in w:
        print("WARN: node 700 (LoraLoader) absent after build — LoRA not applied!", flush=True)
    return w


def run(wf, name):
    t = time.time()
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        print(f"[{name}] POST REJECT {r.status_code}: {r.text[:900]}", flush=True); return None
    pid = r.json()["prompt_id"]
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
            path = f"logs/max_lora_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    # validate the LoRA graph once (no spend)
    test = build(COMBOS[0][1])
    r = requests.post(f"{URL}/prompt", json={"prompt": test}, timeout=30)
    if r.status_code == 200:
        requests.post(f"{URL}/interrupt", timeout=10)
        requests.post(f"{URL}/queue", json={"clear": True}, timeout=10)
        print("[validate] LoRA graph OK (200) — interrupted, no spend", flush=True)
    else:
        print(f"[validate] LoRA graph REJECT {r.status_code}: {r.text[:1000]}", flush=True)
        return 2
    for name, combo in COMBOS:
        wf = build(combo)
        print(f"\n[{name}] lora={combo['lora']} strength={combo['sm']} prefix={combo['prefix']!r}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\nDONE — compare logs/max_lora_*.jpg vs logs/max_sweep_1_base.jpg (no-LoRA baseline)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
