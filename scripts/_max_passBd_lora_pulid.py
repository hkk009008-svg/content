"""Pass-B Design D: man-LoRA + dual-PuLID — the production approach for the
secondary identity (NOT in the original spec; added after Design A NO-GO).

WHY: Design A (masked dual-PuLID) was NO-GO — attn_mask swap-invariant (no
spatial control) AND the man never bound on PuLID-alone (Pass-A 0.487 / S2 0/4 /
Design-A 0.45 cross-floor). REFRAME: the S2/Design-A drivers run LoRA-LESS BY
DESIGN (build_dual -> _inject_identity(..., None, ...) to isolate the PuLID
axis), yet the trained char_lora_man_v1 (TOKman, FAL-trained + pod-placed
2026-06-11) sat unused. Design D adds it:

  - node 700 LoraLoader = char_lora_man_v1 @0.55 (realism config; GLOBAL model
    patch toward TOKman) — the MAN's identity reinforcement.
  - node 100 ApplyPulidFlux = ARIA face (PuLID — aria binds fine on PuLID alone).
  - node 103 ApplyPulidFlux = MAN face (PuLID, as in S2/Design-A).
  - prompt prepended with the LoRA trigger "TOKman" (training-caption convention).

SINGLE LoRA — deliberately NOT the S3 multi-LoRA stack (aria-LoRA + man-LoRA),
which BLED at all strengths. Aria stays PuLID-only; only the man (who won't bind)
gets a LoRA. No masks (Design A's masking had no effect anyway).

GO bar (spec §5 STRICT count): scripts/_arc_score_session.py --halves --artifacts
'logs/passb_d_n*.jpg'; binding_ok BOTH chars >=3/4 strict seeds + VISUAL (a
grey-bearded man on the right, distinct from aria) mandatory.

Run: PYTHONPATH=. .venv/bin/python scripts/_max_passBd_lora_pulid.py --n 1
     [--strength 0.55]  then --n 4. Pod must be RUNNING + ComfyUI UP.
"""
import argparse
import copy

import requests

import quality_max as q
from workflow_selector import get_max_quality_params

import _max_s2_dual_pulid as s2
from _max_passBa_masked_pulid import render_leg  # reuse the money-path-safe loop

URL = s2.URL
MAN_LORA = "char_lora_man_v1.safetensors"   # ComfyUI loras/-relative basename
MAN_TRIGGER = "TOKman"


def build_dual_lora(available, aria_remote, man_remote, strength):
    """Mirror s2.build_dual but inject the man LoRA (node 700) + TOKman trigger.
    Aria PuLID face on 100, man PuLID face on the spliced 103 — identical dual
    topology to S2; the LoRA + trigger are the only deltas."""
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = get_max_quality_params("portrait")
    q._prune_unavailable(w, available, True, True, False)
    # man LoRA on node 700 (global) + aria face on the primary PuLID (node 100)
    q._inject_identity(w, MAN_LORA, aria_remote, params, True, char_lora_strength=strength)
    prompt = f"{MAN_TRIGGER}, {s2.PROMPT}"
    q._inject_conditioning(w, prompt, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)

    if "100" not in w:
        raise SystemExit("ApplyPulidFlux(100) was pruned — dual impossible on this pod")
    if "700" not in w:
        raise SystemExit("LoraLoader(700) absent — man LoRA was NOT injected (check _inject_identity)")
    consumers = [(nid, key) for nid, node in w.items()
                 if isinstance(node, dict)
                 for key, val in node.get("inputs", {}).items()
                 if isinstance(val, list) and len(val) == 2 and str(val[0]) == "100"]
    print(f"post-prune consumers of 100: {consumers}", flush=True)
    w["95"] = {"inputs": {"image": man_remote}, "class_type": "LoadImage"}
    inputs_103 = copy.deepcopy(w["100"]["inputs"])
    inputs_103["model"] = ["100", 0]
    inputs_103["image"] = ["95", 0]
    w["103"] = {"class_type": "ApplyPulidFlux", "inputs": inputs_103}
    for nid, key in consumers:
        w[nid]["inputs"][key] = ["103", 0]

    ins700 = w["700"]["inputs"]
    print(f"  node 700 LoRA: {ins700.get('lora_name')} "
          f"strength_model={ins700.get('strength_model')} "
          f"strength_clip={ins700.get('strength_clip')}", flush=True)
    print(f"  prompt: {prompt[:90]}...", flush=True)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="seeds to render (smoke=1, full=4)")
    ap.add_argument("--strength", type=float, default=0.55, help="man LoRA strength (realism config 0.55)")
    args = ap.parse_args()

    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    aria_remote = s2._upload(s2.ARIA_REF, "passbd_aria.jpg")
    man_remote = s2._upload(s2.MAN_REF, "passbd_man.jpg")
    print(f"uploaded faces: {aria_remote}, {man_remote}", flush=True)
    base = build_dual_lora(available, aria_remote, man_remote, args.strength)

    saved, peak, rc = render_leg(base, s2.SEEDS, args.n, save_prefix="logs/passb_d_n")
    print(f"PASSB-D RENDER LEG: {len(saved)}/{args.n} ok, peak VRAM {peak:.1f} GiB", flush=True)
    if rc == 0 and saved:
        print("Next: VISUAL check (grey-bearded man on right, distinct from aria?) + "
              "scripts/_arc_score_session.py --halves --artifacts 'logs/passb_d_n*.jpg'")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
