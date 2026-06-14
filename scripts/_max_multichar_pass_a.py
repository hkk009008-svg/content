"""Phase-3 driver (runbook docs/RUNBOOK-pod-session-p1-1-s2-2026-06-11.md):
the live multi-char Pass-A acceptance — THROUGH the production dispatch.

Two steps:
  1. Fresh-face secondary: a LoRA-less, identity-stack-free max render of a
     distinct man — doubles as the P1-2 over-cook specimen (no repo image
     carries a non-Aria identity; every test project is Aria-lineage).
     Skipped if logs/p12_fresh_face_man.jpg already exists.
  2. Pass A: phase_c_assembly.generate_ai_broll(quality_tier="max") with
     Aria primary (registered LoRA 0.55 + TOKwoman) + the fresh man as a
     reference-fidelity secondary — exercising dispatch -> generate_ai_broll_max
     -> _inject_secondary_loras (no-op: secondary has no LoRA) ->
     _assemble_max_prompt -> _inject_secondary_faceswap (611 swaps the
     RIGHT-hand face from the man's reference).

Run: PYTHONPATH=. .venv/bin/python scripts/_max_multichar_pass_a.py
"""
import copy
import os
import time

import requests

import quality_max as q
from workflow_selector import get_max_quality_params

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
ARIA_REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
ARIA_LORA = "/Users/hyungkoookkim/Content/logs/char_lora_fal_v2.safetensors"
MAN_PATH = "logs/p12_fresh_face_man.jpg"
MAN_PROMPT = ("cinematic portrait of a middle-aged man, short grey hair, "
              "trimmed grey beard, weathered features, soft window light, "
              "photorealistic, 85mm, looking at camera")
PASS_A_PROMPT = ("a woman with short dark wavy hair on the left and a "
                 "middle-aged man with a grey beard on the right, standing "
                 "together in a sunlit meadow, medium two-shot, both faces "
                 "clearly visible, photorealistic, cinematic")


def _submit_and_save(wf, out_path, tag):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{tag}] queued {pid}", flush=True)
    for _ in range(120):
        time.sleep(12)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"[{tag}] poll err {e}", flush=True)
            continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{tag}] RUN ERROR: {str(st.get('messages'))[:1000]}", flush=True)
            return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print(f"[{tag}] no images", flush=True)
                return None
            img = imgs[-1]
            # gateway resets large transfers transiently (observed live on
            # the first specimen download) — retry; the file is already
            # rendered, only the download is at risk.
            for attempt in range(3):
                try:
                    dl = requests.get(f"{URL}/view", params={
                        "filename": img["filename"],
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")}, timeout=300)
                    dl.raise_for_status()  # a 502 RESPONSE is not success
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[{tag}] download attempt {attempt+1} failed: {e}",
                          flush=True)
                    time.sleep(5)
            else:
                return None
            with open(out_path, "wb") as f:
                f.write(dl.content)
            print(f"[{tag}] SAVED {out_path} ({len(dl.content)/1024/1024:.1f} MB, "
                  f"{(time.time()-t)/60:.1f} min)", flush=True)
            return out_path
    print(f"[{tag}] TIMEOUT", flush=True)
    return None


def render_fresh_face():
    """P1-2 specimen: max graph, NO identity stack (has_character=False)."""
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = get_max_quality_params("portrait")
    q._prune_unavailable(w, available, False, False, False)   # no character stack
    q._inject_identity(w, None, None, params, False)   # no-op (has_character=False)
    q._inject_conditioning(w, MAN_PROMPT, None, None, params, False)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)
    wf = copy.deepcopy(w)
    wf["25"]["inputs"]["noise_seed"] = 880011
    return _submit_and_save(wf, MAN_PATH, "fresh-man")


def main():
    if not os.path.exists(MAN_PATH):
        print("step 1: rendering the fresh-face secondary (P1-2 specimen)…")
        if not render_fresh_face():
            return 1
    else:
        print(f"step 1: {MAN_PATH} exists — skipping")

    print("step 2: Pass A through the production dispatch…", flush=True)
    from phase_c_assembly import generate_ai_broll
    result = generate_ai_broll(
        prompt=PASS_A_PROMPT,
        output_filename="logs/pass_a_multichar.jpg",
        quality_tier="max",
        character_image=ARIA_REF,
        char_lora_path=ARIA_LORA,
        char_lora_strength=0.55,
        char_lora_trigger="TOKwoman",
        identity_anchor="a young woman with shoulder-length dark hair",
        secondary_char_refs=[{
            "char_id": "char_fresh_man",
            "reference": MAN_PATH,
            "identity_anchor": "a middle-aged man with a grey beard",
            "fidelity": "reference",
            "multi_angle_refs": [],
            "lora_path": None,
            "lora_strength": None,
            "trigger": None,
        }],
        # Full classification shape (mirrors cinema/shots/controller.py:748):
        # the 2026-06-11 run passed {"shot_type": "two_shot"} — a key
        # classify_shot_type never reads — and the then-replacement semantics
        # dropped the inferred characters_in_frame → landscape params
        # (identity stack zeroed, arc gate off) → disintegrated artifact.
        shot_hint={"prompt": PASS_A_PROMPT,
                   "characters_in_frame": ["aria", "fresh_man"],
                   "camera": "medium two-shot",
                   "image_api": None},
    )
    print(f"Pass A result: {result}")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
