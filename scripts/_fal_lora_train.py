#!/usr/bin/env python3
"""Train a per-character FLUX LoRA via fal.ai (turnkey) — the fast path.

Zips the 7 character refs, uploads to fal, runs fal-ai/flux-lora-fast-training,
downloads the resulting LoRA. Then we load it into the lean production ComfyUI
pipeline (download to pod) for the realism+identity test. trigger = "TOKwoman".
"""
import glob
import hashlib
import os
import sys
import time
import zipfile

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load FAL_KEY from .env (fal_client reads it from the environment).
for line in open(".env"):
    if line.startswith("FAL_KEY="):
        os.environ["FAL_KEY"] = line.split("=", 1)[1].strip()
        break

import fal_client  # noqa: E402

D = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0"
TRIGGER = "TOKwoman"
STEPS = 2500  # v2: stronger identity (was 1500). Not 3000 — over-fit risk on 6 refs.
ZIP = "/tmp/char_lora_train.zip"
OUT = "logs/char_lora_fal_v2.safetensors"  # v2: never overwrite the proven v1 artifact


def main():
    all_imgs = sorted(glob.glob(f"{D}/*.jpg") + glob.glob(f"{D}/*.png"))
    # v2: de-dup byte-identical refs (canonical.jpg == ref_0.png, same md5) so no
    # single pose is double-weighted in training. Keeps the first (alpha-sorted).
    seen, imgs = {}, []
    for p in all_imgs:
        h = hashlib.md5(open(p, "rb").read()).hexdigest()
        if h in seen:
            print(f"  skip dup {os.path.basename(p)} (== {os.path.basename(seen[h])})", flush=True)
            continue
        seen[h] = p
        imgs.append(p)
    print(f"zipping {len(imgs)} unique refs -> {ZIP}", flush=True)
    with zipfile.ZipFile(ZIP, "w") as z:
        for p in imgs:
            z.write(p, os.path.basename(p))

    print("uploading zip to fal...", flush=True)
    url = fal_client.upload_file(ZIP)
    print(f"uploaded -> {url}", flush=True)

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
    print(f"result keys: {list(result.keys())}", flush=True)

    lora = result.get("diffusers_lora_file") or {}
    lora_url = lora.get("url")
    if not lora_url:
        print(f"NO LoRA url in result: {result}", flush=True); return 1
    print(f"LoRA url: {lora_url}", flush=True)
    r = requests.get(lora_url, timeout=180)
    os.makedirs("logs", exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(r.content)
    print(f"DOWNLOADED {OUT} ({len(r.content)/1024/1024:.1f} MB) | trigger={TRIGGER}", flush=True)
    cfg = result.get("config_file") or {}
    if cfg.get("url"):
        print(f"config: {cfg['url']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
