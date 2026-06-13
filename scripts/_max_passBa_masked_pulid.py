"""Pass-B Phase-3: attention-masked dual-PuLID (spec §2 Design A).

Phase-1 GATE (2026-06-13, scripts/_passb_census.py): the PRODUCTION node
`ApplyPulidFlux` exposes `attn_mask` (optional MASK) and is FLUX-native — so
Design A needs NO new node class (the spec's `ApplyPulidAdvanced` plan was based
on a refuted premise). This driver = `_max_s2_dual_pulid.build_dual` + per-character
attn_mask wiring, nothing else, so attn_mask is the ONLY delta from the S2 dual
baseline (VRAM GO 41.8 GiB, both faces present).

Masking (the experiment): each PuLID identity is restricted to its intended half.
  - node 100 = ARIA  → attn_mask = left.png  (white on LEFT half)
  - node 103 = MAN   → attn_mask = right.png (white on RIGHT half)
Masks: committed 50/50 splits logs/passb_masks/{left,right}.png (3840x2160 =
the S2 generation resolution; clean split is scale-invariant so ApplyPulidFlux
resizing to latent preserves the boundary). attn_mask coord space (pixel vs
latent) and the mask POLARITY (1.0 = apply identity, vs inverted) are resolved
empirically by the N=1 smoke's mandatory VISUAL check below — if faces land on
the wrong halves, swap masks (or InvertMask) and re-smoke before N=4.

Phase 2 (single-char VRAM re-confirm) is FOLDED into the N=1 smoke: the masked
dual adds only 2 LoadImageMask nodes vs the S2 dual, so the N=1 peak VRAM
confirms no regression (≤ ~42.5 GiB) before committing to N=4. Deviation from
the spec's separate Phase 2 — recorded here, saves ~$0.03 + ~5 min, loses no
signal (S2 already bounded VRAM).

GO bar (spec §5, STRICT count): score with
  scripts/_arc_score_session.py --halves --artifacts 'logs/passb_n*.jpg'
binding_ok for BOTH chars on >=3/4 seeds where BOTH halves have a figure read
(NO_FACE-either-half seeds excluded) + VISUAL confirmation mandatory.

Run: PYTHONPATH=. .venv/bin/python scripts/_max_passBa_masked_pulid.py --n 1
     (smoke) then --n 4. Pod must be RUNNING + ComfyUI UP (Phase-1 done).
"""
import argparse
import copy
import time

import requests

import _max_s2_dual_pulid as s2  # reuse URL, _upload, _vram, build_dual, refs, SEEDS

URL = s2.URL
LEFT_MASK = "logs/passb_masks/left.png"     # white LEFT  -> aria (node 100)
RIGHT_MASK = "logs/passb_masks/right.png"   # white RIGHT -> man  (node 103)


def _upload_mask(path, name):
    """Upload a PNG mask to the ComfyUI input dir (png mime, distinct from the
    jpeg face-ref upload)."""
    with open(path, "rb") as f:
        r = requests.post(
            f"{URL}/upload/image", files={"image": (name, f, "image/png")},
            data={"overwrite": "true"}, timeout=40)
        r.raise_for_status()
        return r.json()["name"]


def add_masks(w, swap=False):
    """Wire per-character attn_mask onto the dual stack built by s2.build_dual.

    Default: 100 (aria) <- LEFT mask (96); 103 (man) <- RIGHT mask (98).
    --swap: 100 (aria) <- RIGHT mask; 103 (man) <- LEFT mask. The N=1 smoke
    (2026-06-13) showed the EFFECTIVE attn_mask polarity is INVERTED vs naive
    "white = apply identity": aria's white-LEFT mask rendered aria on the RIGHT
    (aria 0.823 right / man 0.454 cross-floor). So --swap is the corrected
    polarity (aria white-RIGHT mask -> aria excluded right -> aria LEFT).
    96/98 are free IDs in the post-prune graph.
    """
    for nid in ("100", "103"):
        if nid not in w:
            raise SystemExit(f"node {nid} missing — build_dual did not produce the dual stack")
    left_remote = _upload_mask(LEFT_MASK, "passb_mask_left.png")
    right_remote = _upload_mask(RIGHT_MASK, "passb_mask_right.png")
    w["96"] = {"class_type": "LoadImageMask",
               "inputs": {"image": left_remote, "channel": "red"}}
    w["98"] = {"class_type": "LoadImageMask",
               "inputs": {"image": right_remote, "channel": "red"}}
    aria_mask, man_mask = (("98", "96") if swap else ("96", "98"))
    w["100"]["inputs"]["attn_mask"] = [aria_mask, 0]  # aria
    w["103"]["inputs"]["attn_mask"] = [man_mask, 0]   # man
    print(f"  mask polarity: swap={swap} -> aria<-{aria_mask} man<-{man_mask}", flush=True)
    # record the inherited (S2-identical) PuLID params so the delta is auditable
    for nid, who in (("100", "aria/left"), ("103", "man/right")):
        ins = w[nid]["inputs"]
        print(f"  node {nid} ({who}): weight={ins.get('weight')} "
              f"start_at={ins.get('start_at')} end_at={ins.get('end_at')} "
              f"attn_mask={ins.get('attn_mask')}", flush=True)
    return w


def _submit(wf):
    """POST /prompt and return prompt_id, or fail LOUDLY with node_errors.
    A rejected graph returns 200 + node_errors and NO prompt_id — that means
    nothing was queued (no GPU spent), so surface the reason for the NOVEL
    masked wiring instead of a cryptic KeyError."""
    r = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30)
    try:
        j = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if "prompt_id" not in j:
        raise SystemExit(
            "PASSB: /prompt REJECTED the graph (no render spent) — "
            f"error={str(j.get('error'))[:300]} | "
            f"node_errors={str(j.get('node_errors'))[:600]}")
    return j["prompt_id"]


def render_leg(base, seeds, n, save_prefix="logs/passb_n"):
    """S2 money-path-safe render loop, saving to {save_prefix}{i}.jpg. Every
    paid/remote call has a timeout; /view is raise_for_status'd; a
    completed-but-empty run FAILS; sustained gateway loss (err_streak>=6 = ~60s)
    is treated as ComfyUI OOM-death -> NO-GO. save_prefix lets sibling drivers
    (Design D) reuse this loop without clobbering each other's artifacts."""
    peak = 0.0
    saved = []
    for i, seed in enumerate(seeds[:n]):
        wf = copy.deepcopy(base)
        wf["25"]["inputs"]["noise_seed"] = seed
        t = time.time()
        pid = _submit(wf)
        print(f"[n{i+1}] queued {pid} seed={seed}", flush=True)
        done = False
        err_streak = 0
        for _ in range(90):
            time.sleep(10)
            try:
                peak = max(peak, s2._vram())
                h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
                err_streak = 0
            except Exception as e:  # noqa: BLE001
                err_streak += 1
                print(f"[n{i+1}] poll err {e}", flush=True)
                if err_streak >= 6:
                    print(f"PASSB VERDICT: NO-GO (gateway down ~{err_streak}0s at "
                          f"n={i+1} — ComfyUI likely OOM-killed; peak {peak:.1f} GiB)",
                          flush=True)
                    return saved, peak, 1
                continue
            if pid not in h:
                continue
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"[n{i+1}] RUN ERROR: {str(st.get('messages'))[:800]}", flush=True)
                print(f"PASSB VERDICT: NO-GO (error at n={i+1}; peak {peak:.1f} GiB)")
                return saved, peak, 1
            if st.get("completed") or st.get("status_str") == "success":
                outs = h[pid].get("outputs", {})
                node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
                imgs = (node or {}).get("images")
                if not imgs:
                    print(f"[n{i+1}] completed with NO images — failing", flush=True)
                    return saved, peak, 1
                img = imgs[-1]
                for attempt in range(3):
                    try:
                        dl = requests.get(f"{URL}/view", params={
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output")}, timeout=300)
                        dl.raise_for_status()
                        break
                    except Exception as e:  # noqa: BLE001
                        print(f"[n{i+1}] download attempt {attempt+1} failed: {e}", flush=True)
                        time.sleep(5)
                else:
                    print(f"[n{i+1}] download failed 3x — render is pod-side "
                          f"({img['filename']}); continuing", flush=True)
                    done = True
                    break
                path = f"{save_prefix}{i+1}.jpg"
                with open(path, "wb") as f:
                    f.write(dl.content)
                saved.append(path)
                print(f"[n{i+1}] SAVED {path} ({(time.time()-t)/60:.1f} min, "
                      f"peak so far {peak:.1f} GiB)", flush=True)
                done = True
                break
        if not done:
            print(f"[n{i+1}] TIMEOUT")
            return saved, peak, 1
    return saved, peak, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="number of seeds to render (smoke=1, full=4)")
    ap.add_argument("--swap", action="store_true", help="swap mask polarity (corrected per N=1 smoke)")
    args = ap.parse_args()

    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    aria_remote = s2._upload(s2.ARIA_REF, "passb_aria.jpg")
    man_remote = s2._upload(s2.MAN_REF, "passb_man.jpg")
    print(f"uploaded faces: {aria_remote}, {man_remote}", flush=True)
    base = s2.build_dual(available, aria_remote, man_remote)
    add_masks(base, swap=args.swap)

    saved, peak, rc = render_leg(base, s2.SEEDS, args.n)
    print(f"PASSB RENDER LEG: {len(saved)}/{args.n} ok, peak VRAM {peak:.1f} GiB", flush=True)
    if rc == 0 and saved:
        print("Next: VISUAL check (faces on intended halves?) + "
              "scripts/_arc_score_session.py --halves --artifacts 'logs/passb_n*.jpg'")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
