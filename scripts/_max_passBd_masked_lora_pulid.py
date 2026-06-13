"""Pass-B Design D + masking: man-LoRA + dual-PuLID + per-character attn_mask.

THE CONVERGENT EXPERIMENT (director + operator). Two facts, now both established:
  1. Design D made the man BIND for the first time ever (0.870, logs/passb_d_n1.jpg)
     via char_lora_man_v1 @0.55 + dual PuLID + TOKman trigger — but PLACEMENT is
     SWAPPED (man landed LEFT, aria RIGHT; intended = woman-LEFT / man-RIGHT).
  2. attn_mask is FUNCTIONAL (operator d569edd graph-JSON: masked runs differ in
     BYTES) but in Design A it did NOT cleanly PLACE a bound identity: aria landed
     RIGHT under BOTH no-swap AND swap (0.823 vs 0.828) — a swap-INVARIANT OUTCOME
     despite differing renders. swap=True is the INFERRED corrected polarity (white
     = EXCLUDE, from the no-swap run where aria got the white-LEFT mask yet rendered
     RIGHT), but it is a single-observation inference, NOT a confirmed placement.
     The man never bound in Design A (LoRA-less) — "a mask cannot summon a
     non-binding identity" — so placement of a bound identity was never testable.

Design D removed the binding blocker. So this driver = Design D's binding graph +
the masked driver's spatial wiring, swap=True (inferred polarity) default:
  - aria (node 100) <- RIGHT mask  -> aria excluded from right -> aria LEFT
  - man  (node 103) <- LEFT  mask  -> man  excluded from left  -> man  RIGHT
intended woman-LEFT / man-RIGHT — IF the mask can place a BOUND identity AT ALL.
CAVEAT (validation workflow wf_13f32597-e25, adversary): that is UNPROVEN — no mask
config has ever been observed to move a bound identity to its intended slot. This
N=1 is the FIRST real test. If faces stay swapped, masks are placement-inert here
-> pivot to prompt-order/seed (NOT a LoRA-polarity story); do NOT assume --no-swap
will fix it.

KNOWN RISK to read at N=1 (comfyui-mastery prior): the man-LoRA (node 700) is a
GLOBAL model patch; attn_mask gates only the PuLID cross-attention, NOT the LoRA.
So TOKman features may BLEED into aria's (left) half. The mandatory VISUAL check
below must confirm aria's left face is still ARIA, not a man-tinted blend. If it
bleeds, the lever is asymmetric (lower LoRA strength / photoreal man ref / mask
the LoRA path) — flag before N=4.

This is the ONLY delta from the proven Design D driver: add_masks() after
build_dual_lora(). Same money-path-safe render_leg (rejected-graph guard fails $0
before /prompt; all timeouts; err_streak>=6 OOM NO-GO; empty-output FAIL). Stays
on MAX tier deliberately — isolates the PLACEMENT variable from the proven
breakthrough; the over-cook (production-tier quality) is the NEXT, separate burn.

READ ORDER (validation-workflow GUARD 1): run the arc-score halves FIRST, before
any visual verdict — the max-tier over-cook suppresses the grey beard even at 0.870,
so "is there a bearded man on the right" is an unreliable placement proxy.
  scripts/_arc_score_session.py --halves --artifacts 'logs/passb_dm_n*.jpg'
A placement-FIXED result INVERTS the Design-D baseline halves (LEFT man 0.870/aria
0.476; RIGHT aria 0.763/man 0.507) -> expect LEFT aria>=0.75 & man<0.75; RIGHT
man>=0.75 & aria<0.75. Aria's LEFT-half man-score staying LOW also rules out LoRA
bleed (an embedding cross-check more reliable than a visual bleed judgment under
the over-cook). THEN the visual (man right, aria left, no masculine texture on aria).
GO bar (spec §5 STRICT count): binding_ok BOTH chars >=3/4 strict seeds where both
halves have a figure read + visual two-distinct-identities mandatory.

Run: PYTHONPATH=. .venv/bin/python scripts/_max_passBd_masked_lora_pulid.py --n 1
     [--strength 0.55] [--no-swap]   then --n 4. Pod must be RUNNING + ComfyUI UP.
"""
import argparse

import requests

import _max_s2_dual_pulid as s2
from _max_passBa_masked_pulid import add_masks, render_leg
from _max_passBd_lora_pulid import build_dual_lora


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="seeds to render (smoke=1, full=4)")
    ap.add_argument("--strength", type=float, default=0.55,
                    help="man LoRA strength (realism config 0.55)")
    ap.add_argument("--no-swap", dest="swap", action="store_false",
                    help="disable the corrected polarity (default swap=True = "
                         "intended woman-LEFT/man-RIGHT); --no-swap reverts to "
                         "naive white=apply for an A/B placement read")
    ap.set_defaults(swap=True)
    args = ap.parse_args()

    available = set(requests.get(f"{s2.URL}/object_info", timeout=40).json().keys())
    aria_remote = s2._upload(s2.ARIA_REF, "passbdm_aria.jpg")
    man_remote = s2._upload(s2.MAN_REF, "passbdm_man.jpg")
    print(f"uploaded faces: {aria_remote}, {man_remote}", flush=True)

    base = build_dual_lora(available, aria_remote, man_remote, args.strength)
    add_masks(base, swap=args.swap)  # placement layer; swap=True = corrected polarity

    saved, peak, rc = render_leg(base, s2.SEEDS, args.n, save_prefix="logs/passb_dm_n")
    print(f"PASSB-D+MASK RENDER LEG: {len(saved)}/{args.n} ok, peak VRAM {peak:.1f} GiB",
          flush=True)
    if rc == 0 and saved:
        print("Next (GUARD 1 — arc score FIRST, the over-cook hides the beard): "
              "scripts/_arc_score_session.py --halves --artifacts "
              "'logs/passb_dm_n*.jpg' -> a placement-FIX INVERTS the Design-D halves "
              "(expect LEFT aria>=0.75/man<0.75; RIGHT man>=0.75/aria<0.75; aria's "
              "LEFT man-score LOW = no bleed). THEN the visual.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
