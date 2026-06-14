#!/usr/bin/env python3
"""SUPIR over-restoration A/B — same winning seed, softened SUPIR variants.

Isolates SUPIR by reproducing the EXACT harness-winner base (seed 191029263,
node 25) and varying ONLY node 502 SUPIR_sample. One generation per variant
(~4 min) — no new N=8. Reuses quality_max's real injection helpers so every
workflow fix applies, identical to generate_ai_broll_max's build.

current (the over-cooked keyframe): cfg 4.0 / restore_cfg -1.0 / steps 50 / churn 5.
Softening direction: cfg DOWN (less aggressive positive-prompt sharpening),
restore_cfg UP (restoration-guided pullback toward the source -> less hallucinated
detail / fewer artifacts), steps DOWN + churn DOWN (less refinement / added grain).
"""
import copy
import json
import sys
import time

import requests

import quality_max as q

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
WIN_SEED = 191029263  # harness winner (cand2 = base 191028254 + 1*1009), arc 0.839

# Same prompt the harness used, so the base matches.
PROMPT = (
    "Photorealistic cinematic close-up portrait of a single woman, solo, looking "
    "directly into the camera with a warm natural expression, head-and-shoulders "
    "framing, shoulder-length hair, soft natural key light, shallow depth of field, "
    "subtle film grain, 85mm lens, ultra-detailed skin texture. One person only."
)

VARIANTS = {
    "A_moderate": dict(cfg_scale_start=2.8, cfg_scale_end=2.8, restore_cfg=3.0, steps=40, EDM_s_churn=2),
    "B_strong":   dict(cfg_scale_start=2.0, cfg_scale_end=2.0, restore_cfg=5.0, steps=32, EDM_s_churn=1),
}


def build_base():
    with open(REF, "rb") as f:
        face_remote = requests.post(
            f"{URL}/upload/image",
            files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40,
        ).json()["name"]
    print(f"uploaded face ref -> {face_remote}", flush=True)
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())

    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    q._prune_unavailable(w, available, True, True, False)
    q._inject_identity(w, None, face_remote, {}, True)
    q._inject_conditioning(w, PROMPT, None, None, {}, True)
    q._inject_sampling(w, {})
    q._inject_latent_source(w, None, {})
    q._inject_post_passes(w, {}, available)
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = WIN_SEED
    if "502" not in w:
        print("FATAL: node 502 (SUPIR_sample) absent after build — SUPIR pruned?", flush=True)
        sys.exit(2)
    cur = w["502"]["inputs"]
    print(f"base built ({len(w)} nodes); node 502 current: cfg={cur.get('cfg_scale_start')} "
          f"restore_cfg={cur.get('restore_cfg')} steps={cur.get('steps')} churn={cur.get('EDM_s_churn')}",
          flush=True)
    return w


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(90):  # ~18 min ceiling
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] RUN ERROR: {json.dumps(st.get('messages', []))[:1200]}", flush=True)
            return None
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
            path = f"logs/max_tune_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, "
                  f"{(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True)
    return None


def main():
    base = build_base()
    for name, patch in VARIANTS.items():
        wf = copy.deepcopy(base)
        wf["502"]["inputs"].update(patch)
        n = wf["502"]["inputs"]
        print(f"\n[{name}] SUPIR -> cfg={n['cfg_scale_start']} restore_cfg={n['restore_cfg']} "
              f"steps={n['steps']} churn={n['EDM_s_churn']}", flush=True)
        run(wf, name)
    print("\nDONE — compare logs/max_tune_A_moderate.jpg, logs/max_tune_B_strong.jpg "
          "vs the current logs/max_harness_keyframe.jpg", flush=True)


if __name__ == "__main__":
    main()
