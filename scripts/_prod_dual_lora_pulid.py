"""Pass-B Design F (PRODUCTION-tier realism): graft the PROVEN identity stack onto
the PROVEN photoreal sampler chain — to get photorealism AND the man's binding.

WHY (3 quality probes proved the over-cook is STRUCTURAL to the MAX graph):
  - max + dual + LoRA   + SUPIR-on              -> over-cooked (Design D, passb_d_n1)
  - max + dual + no-LoRA + SUPIR-on             -> over-cooked (Design A, passb_n1_swap)
  - max + dual + LoRA + SUPIR-off + FD-off      -> WORSE      (Design E, passb_q_n1)
The over-cook is the MAX base: the hires-fix re-diffusion (node 901, a 2nd sampler
pass on a 1.5x-upscaled latent) + the heavier OptimalStepsScheduler/28-step sampler
(design workflow wf_963a4a8a Lens C, RANK 1). The PRODUCTION graph (pulid.json) ships
photoreal because its sampler chain is CLEAN: BasicScheduler + dpmpp_2m + sgm_uniform
+ 20 steps + PAG + RealESRGAN, with NO hires-fix / SUPIR / FaceDetailer.

NOTE (2026-06-13, ADR-025): pulid.json's single PuLID was a FLUX/SDXL NO-OP when this
driver was written — node 100 was `ApplyPulid` (SDXL-era) on a FLUX UNet, applying ZERO
face lock. That single-PuLID no-op is now FIXED in production (nodes 99/100/101 ->
FLUX-native `ApplyPulidFlux`; validated OFF 0.6205 -> ON 0.8779). This driver is STILL
needed for the distinct goal it serves — DUAL-identity (aria + man) + a per-character
LoRA, which the single-PuLID production fix does not provide. It still has no LoRA node
and no 2nd PuLID in the shipped graph, so this driver GRAFTS the proven FLUX identity
stack onto the clean chain:

  - Upgrade nodes 99/100/101 SDXL->FLUX by COPYING the proven nodes VERBATIM from
    pulid_max.json (ApplyPulidFlux weight=0.85 start_at=0.0 end_at=0.9 fusion=mean ...).
    The node IDs 97/99/100/101/93/112/11 are IDENTICAL across both graphs, so the
    copied input links resolve with NO remapping (adversary's safe method — inherits
    the proven start_at=0.0; production pulid.json is now also start_at=0.0 post-fix,
    so the coarse-identity window is no longer suppressed there either).
  - Inject the man LoRA (node 700, copied from max; model<-112 clip<-11) @0.55 + route
    122.clip -> 700 slot 1 so the LoRA's CLIP/TOKman patch reaches the prompt.
  - Splice a 2nd ApplyPulidFlux (node 103, the MAN) after 100 (aria); man face on 95.
  - Keep pulid.json's RealESRGAN (500/501/502) + sampler chain UNTOUCHED.

GO read (GUARD 1 — arc FIRST): scripts/_arc_score_session.py --halves --artifacts
'logs/passb_prod_n*.jpg'. Man-bind target LEFT man >=~0.75 (cf 0.870 max baseline;
the identity stack is topologically identical so binding should hold). PRIMARY GO =
VISUAL photoreal skin (the realism win). Placement still swapped = expected (separate
axis). If man drops <0.60, lever = asym PuLID weights (--man-weight 1.0) or LoRA 0.65.

Money-path: render_leg UNCHANGED (operator SAFE). NEW GRAPH => Rule #22 before burn.

Run: PYTHONPATH=. .venv/bin/python scripts/_prod_dual_lora_pulid.py --n 1
     [--strength 0.55] [--man-weight 0.85]. Pod RUNNING + ComfyUI UP.
"""
import argparse
import copy
import json

import _max_s2_dual_pulid as s2
from _max_passBa_masked_pulid import render_leg

MAN_LORA = "char_lora_man_v1.safetensors"
MAN_TRIGGER = "TOKman"


def build_prod_dual_lora(strength, man_weight):
    """pulid.json + FLUX-PuLID upgrade (copied from pulid_max.json) + man LoRA + man
    PuLID splice. Pure (no network); the /prompt rejected-graph guard catches any
    missing pod node for $0 at submit."""
    prod = json.load(open("pulid.json"))
    prod.pop("_metadata", None)
    mx = json.load(open("pulid_max.json"))

    # 1. SDXL PuLID nodes -> FLUX, by copying the PROVEN max nodes verbatim. IDs
    #    97/99/100/101/112/11/93 are identical across graphs -> links resolve unchanged.
    for nid in ("99", "100", "101"):
        prod[nid] = copy.deepcopy(mx[nid])
    # 2. man LoRA (node 700, copied from max) -> real file @ realism strength.
    prod["700"] = copy.deepcopy(mx["700"])
    prod["700"]["inputs"]["lora_name"] = MAN_LORA
    prod["700"]["inputs"]["strength_model"] = strength
    prod["700"]["inputs"]["strength_clip"] = strength
    # node 100 (copied) reads model=['700',0]; 700 reads model=['112',0] clip=['11',0]
    # — all present in prod, so the chain 112->700->100 resolves.
    # 3. route the LoRA CLIP patch into the prompt encoder.
    prod["122"]["inputs"]["clip"] = ["700", 1]

    prod["100"]["inputs"]["weight"] = 0.85  # aria PuLID

    # 4. splice the man (103) after aria (100): rewire 100's consumers (PAG 301) to 103.
    consumers = [(nid, key) for nid, node in prod.items()
                 if isinstance(node, dict)
                 for key, val in node.get("inputs", {}).items()
                 if isinstance(val, list) and len(val) == 2 and str(val[0]) == "100"]
    prod["95"] = {"class_type": "LoadImage", "inputs": {"image": None}}  # man ref; set in main
    inputs_103 = copy.deepcopy(prod["100"]["inputs"])
    inputs_103["model"] = ["100", 0]
    inputs_103["image"] = ["95", 0]
    inputs_103["weight"] = man_weight
    prod["103"] = {"class_type": "ApplyPulidFlux", "inputs": inputs_103}
    for nid, key in consumers:
        prod[nid]["inputs"][key] = ["103", 0]
    return prod, consumers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="seeds (smoke=1, full=4)")
    ap.add_argument("--strength", type=float, default=0.55, help="man LoRA strength")
    ap.add_argument("--man-weight", type=float, default=0.85, dest="man_weight",
                    help="man PuLID weight (asym lever: raise to 1.0 if man under-binds)")
    args = ap.parse_args()

    aria_remote = s2._upload(s2.ARIA_REF, "prod_aria.jpg")
    man_remote = s2._upload(s2.MAN_REF, "prod_man.jpg")
    print(f"uploaded faces: {aria_remote}, {man_remote}", flush=True)

    base, consumers = build_prod_dual_lora(args.strength, args.man_weight)
    base["93"]["inputs"]["image"] = aria_remote
    base["95"]["inputs"]["image"] = man_remote
    base["122"]["inputs"]["text"] = f"{MAN_TRIGGER}, {s2.PROMPT}"

    # pre-submit guards — fail $0 before /prompt
    for nid in ("700", "103", "95", "99", "100", "101"):
        if nid not in base:
            raise SystemExit(f"prod build failed — node {nid} missing")
    if base["99"]["class_type"] != "PulidFluxModelLoader":
        raise SystemExit("node 99 not upgraded to PulidFluxModelLoader")
    if not (base["100"]["class_type"] == "ApplyPulidFlux" == base["103"]["class_type"]):
        raise SystemExit("nodes 100/103 not both ApplyPulidFlux")
    if base["100"]["inputs"]["start_at"] != 0.0 or base["103"]["inputs"]["start_at"] != 0.0:
        raise SystemExit("start_at != 0.0 (SDXL inheritance bug) — would suppress binding")
    for bad in ("600", "780", "900", "901", "950"):  # FaceDetailer/DetailDaemon/hires/SUPIR
        if bad in base:
            raise SystemExit(f"over-cook node {bad} present in prod graph — abort")
    if base.get("500", {}).get("class_type") != "ImageUpscaleWithModel":
        raise SystemExit("RealESRGAN node 500 missing/changed — abort")
    print(f"PROD graph: 100(aria 0.85)+103(man {args.man_weight}) ApplyPulidFlux, "
          f"700 LoRA {MAN_LORA}@{args.strength}; 100 consumers rewired to 103: {consumers}",
          flush=True)
    print(f"  prompt: {base['122']['inputs']['text'][:80]}...", flush=True)

    saved, peak, rc = render_leg(base, s2.SEEDS, args.n, save_prefix="logs/passb_prod_n")
    print(f"PROD RENDER LEG: {len(saved)}/{args.n} ok, peak VRAM {peak:.1f} GiB", flush=True)
    if rc == 0 and saved:
        print("Next (GUARD 1 — arc FIRST): scripts/_arc_score_session.py --halves "
              "--artifacts 'logs/passb_prod_n*.jpg' -> man-bind LEFT man >=~0.75 (cf 0.870). "
              "PRIMARY GO = VISUAL photoreal skin (the realism win). Placement swap expected.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
