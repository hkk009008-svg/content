#!/usr/bin/env python3
"""Step 1: run our character through the PRODUCTION tier (pulid.json, 22-node lean).

Confirms whether the production pipeline that made yesterday's realistic clip is
photoreal for OUR character — and measures its identity drift (production's known
weakness). Calls generate_ai_broll(quality_tier='production') directly, which runs
ComfyUI + PuLID on the pod (api_name should be COMFYUI_PULID). Same 4 cinematic
scenes as the max test, so it's a like-for-like realism + drift comparison.
NO LoRA, NO SUPIR/FaceDetailer/etc. — just FLUX + PuLID(1.0) + clean ESRGAN upscale.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phase_c_assembly import generate_ai_broll
from face_validator_gate import score_candidate

REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"

# Cinematic prompts, varied lighting, SAME character. No LoRA trigger (production
# has no LoRA); production's lean FLUX+PuLID + good prompt is the realism source.
SCENES = [
    ("1_window", 770311,
     "Candid cinematic photograph of a woman, solo, close-up, looking at the camera, "
     "soft window light from the side, plain interior wall, natural skin, photographic, "
     "35mm, shallow depth of field. Photorealistic, one person, plain background."),
    ("2_cinematic", 770322,
     "Cinematic film still of a woman, solo, medium close-up, dramatic warm side light, "
     "dark moody plain background, natural skin texture, filmic color, shot on film, "
     "shallow depth of field. Photorealistic, one person, plain dark background."),
    ("3_golden", 770333,
     "Candid photograph of a woman, solo, close-up, warm golden hour light on the face, "
     "soft blurred plain background, natural skin, 85mm, gentle bokeh, authentic. "
     "Photorealistic, one person, plain background."),
    ("4_studio", 770344,
     "Professional photograph of a woman, solo, three-quarter portrait, soft overcast "
     "daylight, plain neutral grey studio backdrop, natural unretouched skin, 50mm, "
     "shallow depth of field. Photorealistic, one person, plain background."),
]


def main():
    scores = []
    for name, seed, prompt in SCENES:
        out = f"logs/prod_scene_{name}.jpg"
        print(f"\n[{name}] seed={seed} -> production tier", flush=True)
        res = generate_ai_broll(
            prompt=prompt, output_filename=out, seed=seed,
            character_image=REF, quality_tier="production",
        )
        if res and os.path.exists(out):
            api = getattr(res, "api_name", "?")
            cs = score_candidate(out, REF, threshold=0.6)
            scores.append((name, cs.arc_score, api))
            print(f"[{name}] SAVED {out} | api={api} | identity arc={cs.arc_score:.3f}", flush=True)
        else:
            print(f"[{name}] FAILED (res={res!r})", flush=True)
    print("\n=== production: realism (eyeball) + identity drift ===", flush=True)
    for n, s, api in scores:
        print(f"  {n}: id {s:.3f}  [{api}]", flush=True)
    if scores:
        vals = [s for _, s, _ in scores]
        print(f"  drift range {min(vals):.3f}-{max(vals):.3f}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
