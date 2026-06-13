"""Pass-B Design E (QUALITY): man-LoRA + dual-PuLID with the SUPIR over-cook pass
DISABLED — the production-realism lever, on the PROVEN binding graph.

WHY (user chose "pivot to quality" after Design-D+masking = NO-GO for placement):
Design D binds the man (0.870, logs/passb_d_n1.jpg) but at MAX tier the SUPIR
restoration pass (quality_max._inject_post_passes, nodes 500-503: a diffusion
re-detailer) over-cooks skin into a cracked/painterly crust — NOT photoreal (the
program goal per PROGRAM-MANUAL). The over-cook source is SUPIR, NOT the
dual-PuLID+LoRA binding graph. So this driver reuses the proven binding graph
(build_dual_lora, UNCHANGED) and flips ONLY params["supir_enabled"]=False, which
takes _inject_post_passes' SUPIR-absent branch (quality_max.py:724 — prunes nodes
500/501/502/503 and re-feeds node 950 from the base VAEDecode chain). ONE variable
(SUPIR on->off), same seed (990011) -> the result compares DIRECTLY to passb_d_n1.

Tests TWO things at once (both are the point):
  1. Does the man still BIND without SUPIR? GATING UNKNOWN — the 0.870 was measured
     on the SUPIR'd output; the base render's identity is unmeasured. If LEFT man
     drops below ~0.75, SUPIR was reinforcing identity and the realism path needs a
     different lever (production pulid.json, or asym weights).
  2. Is the over-cook GONE? Visual: photoreal skin + a crisp grey beard.

FaceDetailer stays ON by default (node 600 re-renders the face region TOWARD the
PuLID embedding = an identity AID, not the cracked-skin culprit). --facedetailer-off
tests its over-cook contribution separately only if SUPIR-off alone isn't enough.

PLACEMENT is still expected SWAPPED (man-LEFT) — this is the QUALITY axis, a
SEPARATE axis from placement (masking already NO-GO). Do not read placement here.

Money-path: render_leg UNCHANGED (operator Rule#22 SAFE eda2e4a/99aea9d). The only
delta from the audited build_dual_lora is a documented flip of a PURE param-getter
(wrap get_max_quality_params -> supir_enabled=False); build_dual_lora resolves the
name at call time, so the wrapper takes effect with no edit to the audited fn and
no money-path change. A $0 offline dry-build asserts the SUPIR nodes are pruned.

GO read (GUARD 1 — arc FIRST): scripts/_arc_score_session.py --halves --artifacts
'logs/passb_q_n*.jpg'. Man-bind survives if LEFT man >=~0.75 (cf. baseline 0.870).
THEN visual: photoreal skin = the realism win.

Run: PYTHONPATH=. .venv/bin/python scripts/_max_passBe_quality_lora_pulid.py --n 1
     [--strength 0.55] [--facedetailer-off]. Pod RUNNING + ComfyUI UP.
"""
import argparse

import requests

import _max_s2_dual_pulid as s2
import _max_passBd_lora_pulid as bd
from _max_passBa_masked_pulid import render_leg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="seeds to render (smoke=1, full=4)")
    ap.add_argument("--strength", type=float, default=0.55, help="man LoRA strength (realism 0.55)")
    ap.add_argument("--facedetailer-off", dest="fd_off", action="store_true",
                    help="also disable FaceDetailer (2nd over-cook source; default ON = identity aid)")
    args = ap.parse_args()

    # Disable SUPIR (+ optionally FaceDetailer) by wrapping the PURE param-getter that
    # build_dual_lora calls — no money-path change, no edit to the audited build_dual_lora.
    # build_dual_lora resolves `get_max_quality_params` as a module global at CALL time,
    # so reassigning bd.get_max_quality_params takes effect for the build below.
    _orig_params = bd.get_max_quality_params

    def _quality_params(shot):
        p = _orig_params(shot)
        p["supir_enabled"] = False
        if args.fd_off:
            p["face_detailer_enabled"] = False
        return p

    bd.get_max_quality_params = _quality_params

    available = set(requests.get(f"{s2.URL}/object_info", timeout=40).json().keys())
    aria_remote = s2._upload(s2.ARIA_REF, "passbq_aria.jpg")
    man_remote = s2._upload(s2.MAN_REF, "passbq_man.jpg")
    print(f"uploaded faces: {aria_remote}, {man_remote}", flush=True)
    print(f"QUALITY: supir_enabled=False  face_detailer_enabled={not args.fd_off}", flush=True)

    base = bd.build_dual_lora(available, aria_remote, man_remote, args.strength)
    supir_left = [n for n in ("500", "501", "502", "503") if n in base]
    if supir_left:
        raise SystemExit(f"SUPIR nodes NOT pruned ({supir_left}) — supir_enabled flip did not take; abort before spend")
    print("  SUPIR nodes pruned (500-503 absent) — over-cook pass OFF", flush=True)

    saved, peak, rc = render_leg(base, s2.SEEDS, args.n, save_prefix="logs/passb_q_n")
    print(f"PASSB-QUALITY RENDER LEG: {len(saved)}/{args.n} ok, peak VRAM {peak:.1f} GiB", flush=True)
    if rc == 0 and saved:
        print("Next (GUARD 1 — arc FIRST): scripts/_arc_score_session.py --halves "
              "--artifacts 'logs/passb_q_n*.jpg' -> man-bind SURVIVES if LEFT man >=~0.75 "
              "(cf. baseline 0.870; placement still swapped = expected, QUALITY axis only). "
              "THEN visual: photoreal skin + crisp grey beard = the realism win.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
