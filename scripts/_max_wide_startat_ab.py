#!/usr/bin/env python3
"""R-MEASURE instrument — MAX-tier WIDE pulid_start_at A/B (0.20 vs 0.0).

OPERATOR-1 independent measurement for director-1's PM7 Carry#1 (the lone ADR-025 cell
the start_at->0.0 sweep missed). MAX `wide` cell carries pulid_start_at=0.20; node 100 is
ApplyPulidFlux (FLUX-native, honors start_at), so 0.20 ACTIVELY delays PuLID binding 20%
into denoising — past the FLUX coarse-identity window where ADR-025 says identity is shaped.

This does NOT change production code (workflow_selector stays at 0.20). It sets node 100's
start_at EXPERIMENTALLY in the graph and renders the SAME ref + SAME wide prompt + SAME seeds
at start_at=0.20 (OFF) vs 0.0 (ON), scoring ArcFace identity each side. The OFF-vs-ON arc delta
is the GO/NO-GO number director-1 needs to land 0.20->0.0 (his lane).

SUPIR OFF (the binding signal is set during sampling, before the SUPIR post-pass; SUPIR off
isolates the start_at variable and is ~5x faster/cheaper). fp16 (51GB RTX 6000 Ada headroom).
Same wide regime as the cell under test: pulid_weight=0.65, end_at=0.9, denoise=0.45.

Output: per-render logs/startat_ab_*.jpg + a logs/max_wide_startat_ab_results.md artifact.
Run:  .venv/bin/python scripts/_max_wide_startat_ab.py
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quality_max as q
from workflow_selector import get_max_quality_params
from face_validator_gate import score_candidate


def _server_url():
    u = os.environ.get("COMFYUI_SERVER_URL")
    if u:
        return u.rstrip("/")
    # fall back to .env
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".env")) as f:
        for line in f:
            if line.startswith("COMFYUI_SERVER_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise SystemExit("COMFYUI_SERVER_URL not set (env or .env)")


URL = _server_url()
os.environ.setdefault("MAX_MODEL_PRECISION", "fp16")

# Reference: prefer the in-project character used by prior validated sweeps; fall back to
# the canonical local ref. The PROMPT must describe the SAME person or ArcFace scoring is
# meaningless — both refs below are the brown-wavy-hair woman character.
_REF_CANDIDATES = [
    "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg",
    "logs/ref_canonical.jpg",
]
REF = next((r for r in _REF_CANDIDATES if os.path.exists(r)), None)
if REF is None:
    raise SystemExit(f"no reference image found among {_REF_CANDIDATES}")

# WIDE shot: subject small/distant in an environment (where start_at binding matters most),
# but a full figure with a still-scoreable face. Matches the woman reference.
PROMPT = (
    "Wide environmental photograph of a real woman standing at a distance in the middle of a "
    "sunlit empty cobblestone plaza, full figure small in the frame, pale stone architecture "
    "around her, shoulder-length wavy brown hair, plain dark crew-neck t-shirt, soft overcast "
    "daylight, photojournalistic, shot on a 35mm camera, authentic, subtle film grain, deep "
    "focus landscape framing. Hyperrealistic photograph, not a render, not CGI, not illustration."
)

START_ATS = [0.20, 0.0]          # OFF (current MAX-wide cell) vs ON (proposed ADR-025 fix)
SEEDS = [990001, 990002, 990003]  # 3 seeds/side to average out seed noise

_face_remote = None
_available = None


def _setup():
    global _face_remote, _available
    with open(REF, "rb") as f:
        _face_remote = requests.post(
            f"{URL}/upload/image", files={"image": ("face_ref.jpg", f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]
    _available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    print(f"REF={REF} -> {_face_remote}; pod classes={len(_available)}", flush=True)


def build(start_at, seed):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = dict(get_max_quality_params("wide"))   # the cell under test (weight 0.65, end_at 0.9)
    params["supir_enabled"] = False                 # isolate the binding signal; faster
    q._prune_unavailable(w, _available, True, False)
    q._inject_identity(w, None, _face_remote, params, True)   # PuLID-only (no LoRA)
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, _available)
    # The variable under test: set node 100 (ApplyPulidFlux) start_at EXPLICITLY.
    if "100" not in w:
        raise SystemExit("node 100 (ApplyPulidFlux) missing — has_character prune dropped PuLID")
    w["100"]["inputs"]["start_at"] = start_at
    if "25" in w:
        w["25"]["inputs"]["noise_seed"] = seed
    return w


def run(wf, name):
    t = time.time()
    pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    print(f"[{name}] queued {pid}", flush=True)
    for _ in range(90):
        time.sleep(10)
        try:
            h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] poll err {e}", flush=True); continue
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print(f"[{name}] RUN ERROR: {str(st.get('messages'))[:900]}", flush=True); return None
        if st.get("completed") or st.get("status_str") == "success":
            outs = h[pid].get("outputs", {})
            node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
            imgs = (node or {}).get("images")
            if not imgs:
                print(f"[{name}] no images", flush=True); return None
            img = imgs[-1]
            dl = requests.get(f"{URL}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")}, timeout=180)
            path = f"logs/startat_ab_{name}.jpg"
            with open(path, "wb") as f:
                f.write(dl.content)
            print(f"[{name}] SAVED {path} ({len(dl.content)/1024/1024:.1f} MB, {(time.time()-t)/60:.1f} min)", flush=True)
            return path
    print(f"[{name}] TIMEOUT", flush=True); return None


def main():
    _setup()
    rows = []  # (start_at, seed, arc, path)
    for sa in START_ATS:
        for seed in SEEDS:
            name = f"sa{sa}_s{seed}"
            wf = build(sa, seed)
            print(f"\n[{name}] start_at={sa} seed={seed}", flush=True)
            path = run(wf, name)
            arc = None
            if path:
                try:
                    cs = score_candidate(path, REF, threshold=0.6)
                    arc = float(cs.arc_score)
                    print(f"[{name}] identity arc={arc:.3f}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[{name}] score err {e}", flush=True)
            rows.append((sa, seed, arc, path))

    # ---- aggregate + persist R-MEASURE artifact ----
    def _mean(sa):
        vals = [r[2] for r in rows if r[0] == sa and r[2] is not None]
        return sum(vals) / len(vals) if vals else None
    off, on = _mean(0.20), _mean(0.0)
    lines = [
        "# MAX-tier WIDE pulid_start_at A/B (R-MEASURE) — operator-1",
        "",
        f"REF: `{REF}`  |  fp16, SUPIR OFF, wide params (pulid_weight=0.65, end_at=0.9)",
        f"Pod: `{URL[:40]}...`  |  seeds: {SEEDS}",
        "",
        "| start_at | seed | arc | image |",
        "|---|---|---|---|",
    ]
    for sa, seed, arc, path in rows:
        lines.append(f"| {sa} | {seed} | {arc if arc is None else f'{arc:.3f}'} | `{path}` |")
    lines += [
        "",
        f"**mean arc — start_at=0.20 (OFF): {off if off is None else f'{off:.4f}'}  |  "
        f"start_at=0.0 (ON): {on if on is None else f'{on:.4f}'}**",
    ]
    if off is not None and on is not None:
        lines.append(f"**delta (ON - OFF): {on - off:+.4f}**  "
                     f"({'ON binds better' if on > off else 'no improvement / regression'})")
    out = "logs/max_wide_startat_ab_results.md"
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nDONE — wrote {out}", flush=True)
    print("\n".join(lines[-4:]), flush=True)


if __name__ == "__main__":
    sys.exit(main())
