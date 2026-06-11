"""S3 spike (spec §S3): multi-LoRA stacking strength sweep.

Primary = Aria LoRA at the validated 0.55 (+ PuLID anchor, the production
MULTI_LORA shape); secondary = man LoRA (char_lora_man_v1, trigger TOKman)
swept over {0.35, 0.45, 0.55} — all inside the §3b per-secondary clamp that
_inject_secondary_loras enforces. Fixed seed across arms isolates the
strength axis. Portrait params to stay comparable with the validated probes
and the S2 dual-PuLID artifacts (the dispatch's two-shot class is `medium`;
the sweep tunes stacking, not shot-class).

Bleed detection happens locally afterwards: arc-score EACH face against its
own ref per arm — cross-character feature leakage shows as paired score
collapse (spec §S3).

Run: PYTHONPATH=. .venv/bin/python scripts/_max_s3_stack_sweep.py
Requires: BOTH LoRAs in the pod's LoraLoader options (Aria placed in Phase 1;
man LoRA scp'd after FAL training) — pre-flight aborts otherwise.
"""
import copy
import time

import requests

import quality_max as q
from workflow_selector import get_max_quality_params

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
ARIA_REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
ARIA_LORA = "char_lora_fal_v2.safetensors"
ARIA_STRENGTH = 0.55      # spec §7.3 registered value
ARIA_TRIGGER = "TOKwoman"
MAN_LORA = "char_lora_man_v1.safetensors"
MAN_TRIGGER = "TOKman"
SWEEP = [0.35, 0.45, 0.55]
SEED = 880221
PROMPT = ("a woman with short dark wavy hair on the left and a middle-aged "
          "man with a grey beard on the right, standing together in a sunlit "
          "meadow, medium two-shot, both faces clearly visible, "
          "photorealistic, cinematic")


def _secondary(strength):
    return {"char_id": "char_fresh_man", "reference": "logs/p12_fresh_face_man.jpg",
            "lora_path": MAN_LORA, "lora_strength": strength,
            "trigger": MAN_TRIGGER, "identity_anchor": "", "multi_angle_refs": [],
            "fidelity": "lora"}


def build(available, aria_remote, strength):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = get_max_quality_params("portrait")
    q._prune_unavailable(w, available, True, False)
    q._inject_identity(w, ARIA_LORA, aria_remote, params, True,
                       char_lora_strength=ARIA_STRENGTH)
    q._inject_secondary_loras(w, [_secondary(strength)])
    prompt = q._assemble_max_prompt(PROMPT, ARIA_TRIGGER, [_secondary(strength)])
    q._inject_conditioning(w, prompt, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)

    n700 = w.get("700", {}).get("inputs", {})
    n701 = w.get("701", {}).get("inputs", {})
    print(f"  700: {n700.get('lora_name')} @ {n700.get('strength_model')} | "
          f"701: {n701.get('lora_name')} @ {n701.get('strength_model')}", flush=True)
    assert n700.get("lora_name") == ARIA_LORA
    assert n701.get("lora_name") == MAN_LORA
    assert abs(float(n701.get("strength_model", -1)) - strength) < 1e-6
    return w


def main():
    info = requests.get(f"{URL}/object_info/LoraLoader", timeout=40).json()
    options = info["LoraLoader"]["input"]["required"]["lora_name"][0]
    for lora in (ARIA_LORA, MAN_LORA):
        if lora not in options:
            print(f"ABORT: {lora} not in LoraLoader options ({len(options)} entries)")
            return 1
    print(f"pre-flight OK: both LoRAs present ({len(options)} entries)", flush=True)

    with open(ARIA_REF, "rb") as f:
        aria_remote = requests.post(
            f"{URL}/upload/image",
            files={"image": ("s3_aria.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())

    saved = []
    for strength in SWEEP:
        print(f"[s3 sec={strength}] building…", flush=True)
        wf = copy.deepcopy(build(available, aria_remote, strength))
        wf["25"]["inputs"]["noise_seed"] = SEED
        t = time.time()
        pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
        print(f"[s3 sec={strength}] queued {pid}", flush=True)
        done = False
        for _ in range(90):
            time.sleep(10)
            try:
                h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
            except Exception as e:  # noqa: BLE001
                print(f"[s3 sec={strength}] poll err {e}", flush=True)
                continue
            if pid not in h:
                continue
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"[s3 sec={strength}] RUN ERROR: {str(st.get('messages'))[:800]}", flush=True)
                return 1
            if st.get("completed") or st.get("status_str") == "success":
                outs = h[pid].get("outputs", {})
                node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
                imgs = (node or {}).get("images")
                if imgs:
                    img = imgs[-1]
                    # gateway resets large transfers transiently — retry;
                    # the render is already pod-side.
                    for attempt in range(3):
                        try:
                            dl = requests.get(f"{URL}/view", params={
                                "filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")}, timeout=300)
                            break
                        except Exception as e:  # noqa: BLE001
                            print(f"[s3 sec={strength}] download attempt "
                                  f"{attempt+1} failed: {e}", flush=True)
                            time.sleep(5)
                    else:
                        print(f"[s3 sec={strength}] download failed 3x — render "
                              f"is pod-side ({img['filename']}); continuing", flush=True)
                        done = True
                        break
                    path = f"logs/s3_stack_sec{int(strength*100)}.jpg"
                    with open(path, "wb") as f:
                        f.write(dl.content)
                    saved.append(path)
                    print(f"[s3 sec={strength}] SAVED {path} "
                          f"({(time.time()-t)/60:.1f} min)", flush=True)
                done = True
                break
        if not done:
            print(f"[s3 sec={strength}] TIMEOUT")
            return 1
    print(f"S3 RENDER LEG COMPLETE: {len(saved)}/{len(SWEEP)} arms saved "
          f"(bleed check = local arc-scoring next)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
