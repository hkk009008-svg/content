#!/usr/bin/env python3
"""Pass-B Phase-1 census + Design-A GATE instrument (R-MEASURE).

Fetches ComfyUI /object_info and emits the Phase-1 census + the Design-A GATE
verdict as a committed, reproducible artifact. The GATE asks one thing: can we
do attention-masked dual-PuLID on a FLUX model? That requires a FLUX-compatible
PuLID applier (a PULIDFLUX-typed pulid input, NOT the SDXL-era PULID type) that
ALSO exposes an attn_mask input.

  - ApplyPulidFlux  : pulid_flux=PULIDFLUX  → FLUX-native (production node)
  - ApplyPulidAdvanced : pulid=PULID        → SDXL/SD15-era; NOT usable on FLUX
                                              regardless of attn_mask presence

Spec premise being tested (SPEC-PASS-B §2.4/§5): "ApplyPulidFlux has no
attn_mask." If the census shows ApplyPulidFlux DOES expose attn_mask, Design A
proceeds via the production node and ApplyPulidAdvanced is moot.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/_passb_census.py \
        [--url http://127.0.0.1:8188] [--out logs/passb_phase1_census_<date>]

URL precedence: --url > $COMFYUI_SERVER_URL > http://127.0.0.1:8188.
Writes <out>.json (machine) + <out>.txt (human); also prints the report.
"""
import argparse
import json
import os
import sys
import urllib.request

CRITICAL = [
    # FLUX PuLID chain (identity)
    "ApplyPulidFlux", "PulidFluxModelLoader", "PulidFluxEvaClipLoader",
    "PulidInsightFaceLoader",
    # Masked-PuLID candidate (SDXL-era; checked for completeness)
    "ApplyPulidAdvanced",
    # Mask nodes for Design A
    "SolidMask", "MaskComposite", "InvertMask", "LoadImageMask", "ImageToMask",
    # Rescue / quality
    "ReActorFaceSwap", "SUPIR_model_loader_v2", "FaceDetailer", "LoadImage",
]


def _pulid_input_type(schema: dict) -> str:
    """Return the declared PuLID-conditioning input type for an applier node."""
    req = (schema or {}).get("input", {}).get("required", {})
    for key in ("pulid_flux", "pulid"):
        if key in req:
            t = req[key][0]
            return f"{key}={t}"
    return "(no pulid input)"


def _has_attn_mask(schema: dict) -> bool:
    opt = (schema or {}).get("input", {}).get("optional", {})
    return "attn_mask" in opt


def analyse(data: dict) -> dict:
    adv = data.get("ApplyPulidAdvanced")
    flux = data.get("ApplyPulidFlux")
    flux_flux_compat = bool(flux) and "pulid_flux" in (flux.get("input", {}).get("required", {}))
    flux_attn = bool(flux) and _has_attn_mask(flux)
    adv_flux_compat = bool(adv) and "pulid_flux" in (adv.get("input", {}).get("required", {}))
    adv_attn = bool(adv) and _has_attn_mask(adv)

    # Design A goal: masked dual-PuLID on FLUX.
    # Path P (preferred): production ApplyPulidFlux exposes attn_mask.
    # Path A (spec's original): ApplyPulidAdvanced is FLUX-compatible AND has attn_mask.
    if flux_flux_compat and flux_attn:
        verdict = "GO"
        route = ("ApplyPulidFlux.attn_mask (PRODUCTION node) — no new class needed; "
                 "delta from the S2 dual driver is wiring a MASK into each "
                 "ApplyPulidFlux.attn_mask input.")
    elif adv_flux_compat and adv_attn:
        verdict = "GO"
        route = "ApplyPulidAdvanced (FLUX-compatible + attn_mask)."
    else:
        verdict = "NO-GO"
        route = ("No FLUX-compatible PuLID applier exposes attn_mask "
                 "(ApplyPulidAdvanced is SDXL-era PULID; ApplyPulidFlux lacks attn_mask). "
                 "Pivot to Design C (ReActor swap rescue).")

    return {
        "total_classes": len(data),
        "critical_presence": {c: (c in data) for c in CRITICAL},
        "ApplyPulidFlux": {
            "present": bool(flux),
            "pulid_input": _pulid_input_type(flux) if flux else None,
            "flux_compatible": flux_flux_compat,
            "has_attn_mask": flux_attn,
        },
        "ApplyPulidAdvanced": {
            "present": bool(adv),
            "pulid_input": _pulid_input_type(adv) if adv else None,
            "flux_compatible": adv_flux_compat,
            "has_attn_mask": adv_attn,
        },
        "design_a_gate": {"verdict": verdict, "route": route},
        "ApplyPulidFlux_schema": (flux or {}).get("input", {}),
        "ApplyPulidAdvanced_schema": (adv or {}).get("input", {}),
    }


def render(report: dict) -> str:
    g = report["design_a_gate"]
    lines = [
        "Pass-B Phase-1 census + Design-A GATE",
        "=" * 44,
        f"TOTAL CLASSES: {report['total_classes']}",
        "",
        "Critical class presence:",
    ]
    for c, ok in report["critical_presence"].items():
        lines.append(f"  {'YES' if ok else 'NO ':>3} {c}")
    fx, adv = report["ApplyPulidFlux"], report["ApplyPulidAdvanced"]
    lines += [
        "",
        "ApplyPulidFlux (production FLUX node):",
        f"  present={fx['present']}  input={fx['pulid_input']}  "
        f"flux_compatible={fx['flux_compatible']}  has_attn_mask={fx['has_attn_mask']}",
        "ApplyPulidAdvanced (SDXL-era candidate):",
        f"  present={adv['present']}  input={adv['pulid_input']}  "
        f"flux_compatible={adv['flux_compatible']}  has_attn_mask={adv['has_attn_mask']}",
        "",
        f"DESIGN-A GATE: {g['verdict']}",
        f"  route: {g['route']}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--out", default=None, help="output path stem (no extension)")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    url = args.url.rstrip("/") + "/object_info"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001 — instrument: surface the failure verbatim
        print(f"census: fetch failed for {url}: {e}", file=sys.stderr)
        return 1

    report = analyse(data)
    text = render(report)
    print(text)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out + ".json", "w") as f:
            json.dump(report, f, indent=1)
        with open(args.out + ".txt", "w") as f:
            f.write(text + "\n")
        print(f"\n[wrote {args.out}.json + .txt]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
