#!/usr/bin/env python3
"""Synthesis test: production realism + ReActor identity lock.

Production gives stunning realism but loses identity (0.43-0.56, different women).
This generates a PRODUCTION keyframe with the character's hair specified (so the
swap lands on the right head), then ReActor-swaps our reference face onto it.
Scores before (production base, expect ~0.5) and after (swapped, expect ~0.8) to
prove the lock. If the swap blends cleanly on a photoreal base = the synthesis.
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phase_c_assembly import generate_ai_broll
from face_validator_gate import score_candidate

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"

# Hair specified so production renders the right head; face comes from the swap.
SCENES = [
    ("1_window", 880711,
     "Candid cinematic photograph of a woman with dark brown wavy shoulder-length hair "
     "and fair skin, solo, close-up, soft window light from the side, plain interior "
     "wall, natural skin, 35mm, shallow depth of field. Photorealistic, one person, "
     "plain background."),
    ("2_cinematic", 880722,
     "Cinematic film still of a woman with dark brown wavy shoulder-length hair and fair "
     "skin, solo, medium close-up, dramatic warm side light, dark moody plain background, "
     "filmic color, shot on film, shallow depth of field. Photorealistic, one person, "
     "plain dark background."),
]


def upload(path, name):
    with open(path, "rb") as f:
        return requests.post(f"{URL}/upload/image", files={"image": (name, f, "image/jpeg")},
                             data={"overwrite": "true"}, timeout=60).json()["name"]


def swap(keyframe_remote, ref_remote, name):
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": keyframe_remote}},
        "2": {"class_type": "LoadImage", "inputs": {"image": ref_remote}},
        "3": {"class_type": "ReActorFaceSwap", "inputs": {
            "enabled": True,
            "input_image": ["1", 0],
            "source_image": ["2", 0],
            "swap_model": "inswapper_128.onnx",
            "facedetection": "retinaface_resnet50",
            "face_restore_model": "codeformer-v0.1.0.pth",
            "face_restore_visibility": 0.8,
            "codeformer_weight": 0.5,
            "detect_gender_input": "no", "detect_gender_source": "no",
            "input_faces_index": "0", "source_faces_index": "0",
            "input_faces_order": "left-right", "source_faces_order": "left-right",
            "console_log_level": 1,
        }},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "synth"}},
    }
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        print(f"[{name}] swap POST REJECT {r.status_code}: {r.text[:600]}", flush=True); return None
    pid = r.json()["prompt_id"]
    for i in range(40):
        time.sleep(6)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception:
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] swap ERROR: {str(st.get('messages'))[:700]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=120)
            path = f"logs/synth_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] swapped -> {path}", flush=True)
            return path
    print(f"[{name}] swap TIMEOUT", flush=True); return None


def main():
    ref_remote = upload(REF, "swapref.jpg")
    print(f"reference uploaded -> {ref_remote}", flush=True)
    rows = []
    for name, seed, prompt in SCENES:
        kf = f"logs/prodbase_{name}.jpg"
        print(f"\n[{name}] production keyframe (hair-specified)...", flush=True)
        res = generate_ai_broll(prompt=prompt, output_filename=kf, seed=seed,
                                character_image=REF, quality_tier="production")
        if not res or not os.path.exists(kf):
            print(f"[{name}] production FAILED ({res!r})", flush=True); continue
        base = score_candidate(kf, REF, threshold=0.6).arc_score
        kf_remote = upload(kf, f"prodbase_{name}.jpg")
        out = swap(kf_remote, ref_remote, name)
        sw = score_candidate(out, REF, threshold=0.6).arc_score if out else None
        rows.append((name, base, sw))
        print(f"[{name}] base id={base:.3f} -> swapped id={sw if sw is None else round(sw,3)}", flush=True)
    print("\n=== synthesis: production base -> ReActor-swapped ===", flush=True)
    for n, b, s in rows:
        print(f"  {n}: {b:.3f} -> {s if s is None else round(s,3)}", flush=True)
    print("DONE — compare logs/prodbase_*.jpg (production) vs logs/synth_*.jpg (swapped)", flush=True)


if __name__ == "__main__":
    main()
