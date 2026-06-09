#!/usr/bin/env python3
"""Free pre-flight for the max-tier full harness (N=8 + Veo). NO GPU/Veo spend.

Verifies the two load-bearing assumptions before committing the costly run:
  1. Local candidate scoring works on THIS Mac — ArcFace identity + LAION
     aesthetic. The prior 4K-image proof used _max_run_image.py, which did NOT
     exercise score_candidate; the N=8 best-of path depends on it. We score the
     two known face refs of the same person against each other; expect has_arc.
  2. Veo lands on the *vertex* backend — generate_audio is silently dropped on
     the Gemini fallback, so native audio is impossible off Vertex. Construction
     only (no generate call) — zero spend.
Plus: COMFYUI_SERVER_URL set (pod gateway) and the face ref exists.

Exit 0 = all green (safe to run the harness); non-zero = a blocker to surface.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REF_A = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/canonical.jpg"
REF_B = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"

problems = []
print("=" * 72)
print("MAX-TIER HARNESS PRE-FLIGHT (no spend)")
print("=" * 72)

# 1. Imports — catch a broken production path before anything else.
try:
    from quality_max import generate_ai_broll_max  # noqa: F401
    from face_validator_gate import score_candidate
    print("[1] import generate_ai_broll_max + score_candidate: OK")
except Exception as e:  # noqa: BLE001
    print(f"[1] IMPORT FAILED: {e!r}")
    problems.append(f"import: {e!r}")
    print("\nABORT — cannot proceed without the production path importing.")
    sys.exit(1)

# 2. COMFYUI_SERVER_URL (pod gateway)
try:
    from config import settings
    url = settings.comfyui_server_url
    if url:
        print(f"[2] COMFYUI_SERVER_URL: set ({url[:48]}...)")
    else:
        print("[2] COMFYUI_SERVER_URL: MISSING")
        problems.append("COMFYUI_SERVER_URL unset")
except Exception as e:  # noqa: BLE001
    print(f"[2] settings load failed: {e!r}")
    problems.append(f"settings: {e!r}")

# 3. Face ref present
if os.path.exists(REF_B):
    print(f"[3] face ref present: {REF_B}")
else:
    print(f"[3] face ref MISSING: {REF_B}")
    problems.append(f"face ref missing: {REF_B}")

# 4. Local scoring — score same person (canonical vs lighting_outdoor).
#    Expect has_arc=True and a non-trivial arc score; aesthetic present.
if os.path.exists(REF_A) and os.path.exists(REF_B):
    try:
        cs = score_candidate(REF_A, REF_B, threshold=0.0)
        print(f"[4] local scoring ran: arc={cs.arc_score:.3f} has_arc={cs.has_arc} | "
              f"aes={cs.aesthetic_score:.3f} has_aes={cs.has_aesthetic} | comp={cs.composite:.3f}")
        if not cs.has_arc:
            print("    WARNING: ArcFace did not load locally — best-of-N selection "
                  "would be aesthetic-only (run still completes, identity not gated).")
            problems.append("ArcFace unavailable locally (degraded selection)")
        if not cs.has_aesthetic:
            print("    WARNING: aesthetic scorer unavailable locally.")
    except Exception as e:  # noqa: BLE001
        print(f"[4] local scoring RAISED: {e!r}")
        problems.append(f"scoring raised: {e!r}")
else:
    print("[4] skipped (a ref missing)")

# 5. Veo backend — MUST be vertex for native audio. Construction only, no spend.
try:
    from veo_native import VeoNativeAPI
    api = VeoNativeAPI()
    backend = getattr(api, "_backend", None)
    model = getattr(api, "_model", None)
    if backend == "vertex":
        print(f"[5] Veo backend: vertex (model={model}) — native audio possible: OK")
    else:
        print(f"[5] Veo backend: {backend!r} (model={model}) — NOT vertex; "
              f"generate_audio would be silently dropped.")
        problems.append(f"Veo backend {backend!r} != vertex (no native audio)")
except Exception as e:  # noqa: BLE001
    print(f"[5] VeoNativeAPI construction failed: {e!r}")
    problems.append(f"veo construct: {e!r}")

print("=" * 72)
if problems:
    print(f"PRE-FLIGHT: {len(problems)} concern(s):")
    for p in problems:
        print(f"  - {p}")
    # ArcFace-degraded is a soft concern; a hard blocker is anything else.
    hard = [p for p in problems if "degraded" not in p]
    sys.exit(2 if hard else 0)
print("PRE-FLIGHT: ALL GREEN — safe to run the harness.")
sys.exit(0)
