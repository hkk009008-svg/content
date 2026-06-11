#!/usr/bin/env python3
"""S3 prerequisite: train the SECOND registered character LoRA (the P1-2
fresh-face man) via fal.ai — user-funded, authorized 2026-06-11.

Mirrors the two proven recipes end-to-end:
  1. domain/character_manager._generate_multi_angle_refs — 5 Kontext Max Multi
     variants (same prompts/params) from the single canonical
     logs/p12_fresh_face_man.jpg, into logs/man_lora_refs/.
  2. scripts/_fal_lora_train.py (v2) — md5-dedup'd zip ->
     fal-ai/flux-lora-fast-training, trigger "TOKman", 2500 steps,
     create_masks; downloads logs/char_lora_man_v1.safetensors.

NOTE (recorded for the S3 verdict): the canonical is the P1-2 over-cook
specimen (painterly). Identity CONSISTENCY is what the S3 bleed sweep needs,
so this is fit-for-spike; a production-grade 2nd character should re-train
from a photoreal canonical.

Run: PYTHONPATH=. .venv/bin/python scripts/_fal_man_lora_train.py
"""
import hashlib
import os
import sys
import time
import urllib.request
import zipfile

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for line in open(".env"):
    if line.startswith("FAL_KEY="):
        os.environ["FAL_KEY"] = line.split("=", 1)[1].strip()
        break

import fal_client  # noqa: E402

CANONICAL = "logs/p12_fresh_face_man.jpg"
REF_DIR = "logs/man_lora_refs"
TRIGGER = "TOKman"
STEPS = 2500  # match the proven Aria v2 recipe (6 refs, no over-fit observed)
ZIP = "/tmp/man_lora_train.zip"
OUT = "logs/char_lora_man_v1.safetensors"

# Exact prompt set from domain/character_manager._generate_multi_angle_refs
ANGLE_CONFIGS = [
    {"name": "angle_45", "prompt": (
        "Keep this exact person's face identical. Same person, same clothing, same lighting. "
        "Three-quarter view, face turned 45 degrees to the right. "
        "Photorealistic portrait, 8K, cinematic studio lighting.")},
    {"name": "angle_profile", "prompt": (
        "Keep this exact person's face identical. Same person, same clothing, same lighting. "
        "Side profile view, face turned 90 degrees showing left side. "
        "Photorealistic portrait, 8K, cinematic studio lighting.")},
    {"name": "angle_back", "prompt": (
        "Keep this exact person identical. Same clothing, same hairstyle visible from behind. "
        "Back of head and shoulders view. "
        "Photorealistic, 8K, cinematic studio lighting.")},
    {"name": "expression_smile", "prompt": (
        "Keep this exact person's face identical. Same person, same clothing, same lighting. "
        "Warm genuine smile, eyes slightly crinkled, direct eye contact with camera. "
        "Photorealistic portrait, 8K, cinematic studio lighting.")},
    {"name": "lighting_outdoor", "prompt": (
        "Keep this exact person's face identical. Same person, same clothing. "
        "Natural outdoor golden hour lighting, warm side light from the left, soft shadows. "
        "Photorealistic portrait, 8K, cinematic natural lighting.")},
]


def _record_kontext_cost(op):
    try:
        from cost_tracker import CostTracker
        CostTracker().record_api_call("FLUX_KONTEXT", operation=op)
    except Exception:
        print(f"  cost record skipped for {op} (non-critical)", flush=True)


def generate_refs():
    os.makedirs(REF_DIR, exist_ok=True)
    refs = [CANONICAL]
    canonical_url = fal_client.upload_file(CANONICAL)
    print(f"canonical uploaded -> {canonical_url}", flush=True)
    for cfg in ANGLE_CONFIGS:
        out_path = os.path.join(REF_DIR, f"{cfg['name']}.jpg")
        if os.path.exists(out_path):
            print(f"  [ANGLE] {cfg['name']} exists — skipping", flush=True)
            refs.append(out_path)
            continue
        try:
            result = fal_client.subscribe(
                "fal-ai/flux-pro/kontext/max/multi",
                client_timeout=180,  # mirror character_manager.py:304 — a stalled FAL queue must not hang the run
                arguments={
                    "prompt": (
                        "PRESERVE IDENTITY: Keep this exact person's face, hair, skin, "
                        "and all physical features identical to @Image1. "
                        f"{cfg['prompt']}"),
                    "image_urls": [canonical_url],
                    "guidance_scale": 4.0,
                    "aspect_ratio": "3:4",
                    "output_format": "jpeg",
                    "num_images": 1,
                },
            )
            urllib.request.urlretrieve(result["images"][0]["url"], out_path)
            refs.append(out_path)
            print(f"  [ANGLE] generated {cfg['name']}", flush=True)
            _record_kontext_cost("man_lora_ref")
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] {cfg['name']} failed: {e} — continuing", flush=True)
    return refs


def main():
    if os.path.exists(OUT):
        # operator F1 (02:01:00Z): training is NOT idempotent — a re-run
        # re-spends the FAL fee and overwrites the validated artifact.
        print(f"ABORT: {OUT} already exists — delete it explicitly to retrain")
        return 1
    if not os.path.exists(CANONICAL):
        print(f"canonical missing: {CANONICAL}"); return 1
    refs = generate_refs()
    if len(refs) < 4:
        print(f"only {len(refs)} refs — too thin to train; aborting"); return 1

    seen, imgs = {}, []
    for p in refs:
        h = hashlib.md5(open(p, "rb").read()).hexdigest()
        if h in seen:
            print(f"  skip dup {os.path.basename(p)}", flush=True)
            continue
        seen[h] = p
        imgs.append(p)
    print(f"zipping {len(imgs)} unique refs -> {ZIP}", flush=True)
    with zipfile.ZipFile(ZIP, "w") as z:
        for p in imgs:
            z.write(p, os.path.basename(p))

    url = fal_client.upload_file(ZIP)
    print(f"zip uploaded -> {url}", flush=True)

    def on_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in (update.logs or []):
                print(f"  [fal] {log.get('message','')}", flush=True)

    t0 = time.time()
    print(f"submitting fal-ai/flux-lora-fast-training (trigger={TRIGGER!r}, steps={STEPS})...", flush=True)
    result = fal_client.subscribe(
        "fal-ai/flux-lora-fast-training",
        arguments={
            "images_data_url": url,
            "trigger_phrase": TRIGGER,
            "steps": STEPS,
            "create_masks": True,
        },
        with_logs=True,
        on_queue_update=on_update,
    )
    print(f"\nfal training done ({(time.time()-t0)/60:.1f} min)", flush=True)

    lora = result.get("diffusers_lora_file") or {}
    lora_url = lora.get("url")
    if not lora_url:
        print(f"NO LoRA url in result: {result}", flush=True); return 1
    r = requests.get(lora_url, timeout=180)
    with open(OUT, "wb") as f:
        f.write(r.content)
    print(f"DOWNLOADED {OUT} ({len(r.content)/1024/1024:.1f} MB) | trigger={TRIGGER}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
