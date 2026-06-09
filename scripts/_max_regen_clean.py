#!/usr/bin/env python3
"""Step 2: regenerate clean-neck seeds with the now-baked A SUPIR settings.

The harness winner (seed 191029263, arc 0.839) drew the WORST neck. The
8-candidate neck montage showed the artifact is seed-specific; two other
high-identity candidates have clean necks. Regenerating them reproduces the
SAME base (same seed/prompt/precision) -> same clean neck -> now finished with
A's softened SUPIR (already in pulid_max.json node 502) -> natural skin.
Scores each locally (ArcFace) so we pick the best clean-neck + identity.
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

# Studio prompt: PLAIN backdrop + solo (Veo's RAI blocks generated video with
# background people — both env-background regens were filtered 3/3). Plain
# crew-neck top + bare neck also avoids the collar/neck artifact.
PROMPT = (
    "Photorealistic cinematic studio headshot of a single woman, solo, alone, "
    "looking directly into the camera with a warm natural expression, "
    "head-and-shoulders framing, shoulder-length wavy hair, plain dark crew-neck "
    "top, smooth bare neck, plain neutral grey seamless studio backdrop, soft "
    "natural key light, shallow depth of field, 85mm lens. Solo studio portrait, "
    "no other people, no background scene, plain empty backdrop."
)

# Fresh seeds (the env-background seeds are RAI-blocked); pick the cleanest.
SEEDS = [("studio1", 770811), ("studio2", 770822)]


def build_base():
    with open(REF, "rb") as f:
        face_remote = requests.post(
            f"{URL}/upload/image", files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    print(f"uploaded face ref -> {face_remote}", flush=True)
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    # REAL portrait params (same as the harness) so the base reproduces the
    # clean-neck candidate exactly; with the bake these now carry A's SUPIR
    # cfg=2.8/steps=40, and restore_cfg=3.0/churn=2 come from pulid_max.json.
    params = get_max_quality_params("portrait")
    q._prune_unavailable(w, available, True, False)
    q._inject_identity(w, None, face_remote, params, True)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)
    n = w["502"]["inputs"]
    print(f"baked SUPIR (from pulid_max.json): cfg={n['cfg_scale_start']} "
          f"restore_cfg={n['restore_cfg']} steps={n['steps']} churn={n['EDM_s_churn']}", flush=True)
    return w


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(90):
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
            path = f"logs/max_clean_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    base = build_base()
    for name, seed in SEEDS:
        wf = copy.deepcopy(base)
        wf["25"]["inputs"]["noise_seed"] = seed
        print(f"\n[{name}] seed={seed}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            print(f"[{name}] identity arc={cs.arc_score:.3f} has_arc={cs.has_arc}", flush=True)
    print("\nDONE — inspect logs/max_clean_s191034308.jpg + logs/max_clean_s191031281.jpg necks", flush=True)


if __name__ == "__main__":
    main()
