#!/usr/bin/env python3
"""Test the fal char-LoRA in the LEAN PRODUCTION pipeline (pulid.json + LoRA).

The synthesis goal: production realism (lean pulid.json, ESRGAN upscale, no SUPIR/
FaceDetailer/ReActor) + NATIVE identity from the char-LoRA. Injects a LoraLoader
(112->100.model, 11->122.clip) loading the char-LoRA, prompts with the trigger.
Keeps production PuLID as a second identity anchor. 4 cinematic scenes; scores
identity (want all ~0.8 = drift solved WITH production realism).
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from face_validator_gate import score_candidate

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
LORA = os.environ.get("FALPROD_LORA", "char_lora_fal.safetensors")  # pod loras dir; override for v2
TAG = os.environ.get("FALPROD_TAG", "")     # output prefix, e.g. "v2_" -> logs/falprod_v2_<scene>.jpg
TRIGGER = "TOKwoman"
LORA_STRENGTH = float(os.environ.get("FALPROD_LORA_STRENGTH", "1.0"))

SCENES = [
    ("1_window", 770311, "candid cinematic photograph, close-up, looking at camera, soft window light from the side, plain interior wall, natural skin, 35mm, shallow depth of field. Photorealistic, one person, plain background."),
    ("2_cinematic", 770322, "cinematic film still, medium close-up, dramatic warm side light, dark moody plain background, filmic color, shot on film. Photorealistic, one person, plain dark background."),
    ("3_golden", 770333, "candid photograph, close-up, warm golden hour light on the face, soft blurred plain background, natural skin, 85mm, gentle bokeh. Photorealistic, one person, plain background."),
    ("4_studio", 770344, "professional photograph, three-quarter portrait, soft overcast daylight, plain neutral grey studio backdrop, natural unretouched skin, 50mm. Photorealistic, one person, plain background."),
]


def upload(path, name):
    with open(path, "rb") as f:
        return requests.post(f"{URL}/upload/image", files={"image": (name, f, "image/jpeg")},
                             data={"overwrite": "true"}, timeout=60).json()["name"]


def build(face_remote, prompt, seed):
    w = json.load(open("pulid.json"))
    # inject a LoRA on the FLUX UNet + CLIP: 112->777->100.model, 11->777->122.clip
    w["777"] = {"class_type": "LoraLoader", "inputs": {
        "lora_name": LORA, "strength_model": LORA_STRENGTH, "strength_clip": LORA_STRENGTH,
        "model": ["112", 0], "clip": ["11", 0]}}
    w["100"]["inputs"]["model"] = ["777", 0]
    w["122"]["inputs"]["clip"] = ["777", 1]
    # production-style identity + inject scene
    w["100"]["inputs"]["weight"] = 1.0
    w["100"]["inputs"]["start_at"] = 0.2
    w["93"]["inputs"]["image"] = face_remote
    w["122"]["inputs"]["text"] = f"{TRIGGER}, {prompt}"
    w["25"]["inputs"]["noise_seed"] = seed
    return w


def run(wf, name):
    t = time.time()
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        print(f"[{name}] POST REJECT {r.status_code}: {r.text[:800]}", flush=True); return None
    pid = r.json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for i in range(90):
        time.sleep(10)
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
            path = f"logs/falprod_{TAG}{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    face_remote = upload(REF, "face_ref.jpg")
    print(f"face uploaded -> {face_remote}; LoRA={LORA} trigger={TRIGGER}", flush=True)
    rows = []
    for name, seed, prompt in SCENES:
        wf = build(face_remote, prompt, seed)
        print(f"\n[{name}] production + char-LoRA, seed={seed}", flush=True)
        path = run(wf, name)
        if path:
            cs = score_candidate(path, REF, threshold=0.6)
            rows.append((name, cs.arc_score))
            print(f"[{name}] identity arc={cs.arc_score:.3f}", flush=True)
    print("\n=== production + fal char-LoRA: identity drift ===", flush=True)
    for n, s in rows:
        print(f"  {n}: {s:.3f}", flush=True)
    if rows:
        vals = [s for _, s in rows]
        print(f"  range {min(vals):.3f}-{max(vals):.3f}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
