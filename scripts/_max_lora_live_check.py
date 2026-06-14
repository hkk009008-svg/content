"""Phase-2 probe (runbook docs/RUNBOOK-pod-session-p1-1-s2-2026-06-11.md):
first live render with the pod-placed Aria LoRA — single char, N=1.

Validates end-to-end what slice 2 changed about the single-char path:
basename lora_name (node 700 must LOAD char_lora_fal_v2.safetensors),
registered strength 0.55, TOKwoman trigger prepended via _assemble_max_prompt.
PRE-FLIGHT aborts if the LoRA is not yet in the pod's LoraLoader options
(Phase 1 placement not done).

Run: PYTHONPATH=. .venv/bin/python scripts/_max_lora_live_check.py
(repo root on the path — quality_max lives at root, not scripts/)
"""
import copy
import time

import requests

import quality_max as q
from workflow_selector import get_max_quality_params

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
LORA = "char_lora_fal_v2.safetensors"
STRENGTH = 0.55           # spec §7.3: manual registration value (v2 sweep best)
TRIGGER = "TOKwoman"      # registered trigger (project.json char_lora_triggers)
PROMPT = ("cinematic portrait of a woman, short dark wavy bob, soft window "
          "light, photorealistic, 85mm")
SEED = 770833


def main():
    # --- pre-flight: LoRA actually on the pod? -----------------------------
    info = requests.get(f"{URL}/object_info/LoraLoader", timeout=40).json()
    options = info["LoraLoader"]["input"]["required"]["lora_name"][0]
    if LORA not in options:
        print(f"ABORT: {LORA} not in the pod's LoraLoader options "
              f"({len(options)} entries) — Phase 1 placement has not landed.")
        return 1
    print(f"pre-flight OK: {LORA} present in LoraLoader options")

    with open(REF, "rb") as f:
        face_remote = requests.post(
            f"{URL}/upload/image",
            files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    print(f"uploaded face ref -> {face_remote}", flush=True)

    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = get_max_quality_params("portrait")

    q._prune_unavailable(w, available, True, True, False)
    q._inject_identity(w, LORA, face_remote, params, True,
                       char_lora_strength=STRENGTH)
    prompt = q._assemble_max_prompt(PROMPT, TRIGGER, None)
    print(f"assembled prompt: {prompt[:80]}...")
    q._inject_conditioning(w, prompt, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)

    n700 = w.get("700", {}).get("inputs", {})
    print(f"node 700: lora_name={n700.get('lora_name')} "
          f"strength={n700.get('strength_model')}/{n700.get('strength_clip')}")
    assert n700.get("lora_name") == LORA, "basename normalization broke"

    wf = copy.deepcopy(w)
    wf["25"]["inputs"]["noise_seed"] = SEED
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"queued {pid}", flush=True)
    for _ in range(90):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"poll err {e}", flush=True)
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"RUN ERROR: {str(st.get('messages'))[:1000]}", flush=True)
            return 1
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print("no images", flush=True)
                return 1
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = "logs/max_lora_live_check.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, "
                  f"{(time.time()-t)/60:.1f} min)", flush=True)
            return 0
    print("TIMEOUT", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
