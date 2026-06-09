#!/usr/bin/env python3
"""30s talking head — NEW face (no PuLID), 9:16 vertical. Direct: FLUX face -> TTS -> Hedra.

Generates a fresh person (has_character=False -> PuLID stack pruned, pure FLUX from the prompt),
forced to 9:16 via _inject_aspect, applying the §5.4 clean-bg + neck lessons positively. Then
ElevenLabs TTS (male voice for a male face) for the ~30s monologue, then Hedra Character-3
generation-mode talking head at aspect_ratio=9:16.
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quality_max as q
from workflow_selector import get_max_quality_params
from config.settings import get_settings
from audio.dialogue import generate_dialogue_voiceover
from hedra_native import HedraAPI

URL = get_settings().comfyui_server_url.rstrip("/")
os.environ.setdefault("MAX_MODEL_PRECISION", "fp16")
os.makedirs("logs", exist_ok=True)
SEED = 20260609

FACE_PROMPT = (
    "Photorealistic cinematic vertical portrait of a single man, solo, mid-30s, short dark "
    "hair, light stubble, looking directly into the camera with a calm confident expression, "
    "head-and-shoulders framing, soft natural key light, shallow depth of field, subtle film "
    "grain, 85mm lens, ultra-detailed skin texture, natural proportional neck and shoulders, "
    "well-defined collarbone, anatomically correct proportions. One person only, alone, plain "
    "softly-lit neutral studio backdrop, no other people in frame."
)
NARRATIVE = (
    "They told me this city forgets everyone eventually. Maybe that's true. But standing here, "
    "watching the lights come on one by one, I've started to think forgetting is just another "
    "word for starting over. I came here with nothing — a name, and a promise I made to myself. "
    "And every night since, this skyline has felt a little more like mine. Tonight, for the first "
    "time, I'm not afraid of being forgotten. I'm ready to be remembered."
)
VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # ElevenLabs "Adam" (male)


def gen_face():
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("portrait"))
    # PHOTOREAL config: strip the enhancement stack that over-cooks a no-PuLID FLUX face
    # (detail_daemon / FreeU / FaceDetailer / hires / SUPIR are co-tuned for a PuLID-anchored
    # base; on a bare FLUX face they amplify texture into an oil-painting look). Pure FLUX base.
    params["supir_enabled"] = False
    params["detail_daemon_amount"] = 0.0
    params["freeu_b1"] = 1.0
    params["freeu_b2"] = 1.0
    params["freeu_s1"] = 0.0
    params["freeu_s2"] = 0.0
    params["face_detailer_enabled"] = False
    params["hires_fix_enabled"] = False
    params["guidance"] = 3.2
    q._prune_unavailable(w, available, False, False)          # has_character=False -> drop PuLID stack
    q._inject_identity(w, None, None, params, False)
    q._inject_conditioning(w, FACE_PROMPT, None, None, params, False)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)
    q._inject_aspect(w, "9:16")                               # transpose to portrait
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = SEED
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": w}, timeout=30).json()["prompt_id"]
    print(f"   face queued {pid}", flush=True)
    for _ in range(110):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"   poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"   FACE RUN ERROR: {str(st.get('messages'))[:800]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print("   face: no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = "logs/talkinghead2_face_photoreal.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"   face SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print("   face TIMEOUT", flush=True); return None


def main():
    print("[1/3] generating NEW 9:16 face (no PuLID, fresh person) ...", flush=True)
    face = gen_face()
    if not face:
        print("FATAL: face gen failed", flush=True); return 1

    print(f"[2/3] generating ~30s audio ({len(NARRATIVE.split())} words, ElevenLabs Adam) ...", flush=True)
    audio = generate_dialogue_voiceover(
        [{"character_id": "narrator", "text": NARRATIVE, "delivery": "natural"}],
        [{"id": "narrator", "name": "Narrator", "voice_id": VOICE_ID}],
        output_filename="logs/talkinghead2_audio.mp3",
    )
    if not audio:
        print("FATAL: audio gen failed", flush=True); return 1
    print(f"[2/3] audio -> {audio}", flush=True)

    print("[3/3] Hedra Character-3 talking head @ 9:16 ...", flush=True)
    out = HedraAPI().generate_talking_head(
        face, audio, "logs/talkinghead2_photoreal_9x16.mp4", aspect_ratio="9:16", resolution="720p",
    )
    print(f"[3/3] DONE -> {out}", flush=True)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
