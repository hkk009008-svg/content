"""Environmental foley generation via Stability AI Stable Audio 2.0.

Single-provider path for this slice (T1). Multi-layer and ElevenLabs
paths are out of scope and can be added in T2+ if needed.

Public API:
  _build_foley_prompt(scene_foley_descriptor)  — prompt-vibe mapping
  generate_stability_foley(...)                — Stability AI REST call
                                                 with caller-controlled
                                                 caching and graceful failure

Previously existed at 48f2a24~1:audio/foley.py, deleted at 48f2a24
for zero live callers. Re-added here with trimmed T1 scope for Stability
path only; pipeline wiring comes in T2.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from config.settings import settings


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_foley_prompt(scene_foley_descriptor: str) -> str:
    """Elaborated Stability AI prompt for a foley environment descriptor.

    Known environments get a richer producer-grade prompt; unknown
    descriptors fall through to the raw string (still useful as a direct
    prompt to Stable Audio).
    """
    env_prompts = {
        "rain": (
            "Heavy rain falling on glass and pavement, steady rhythmic patter, "
            "puddles splashing, distant thunder rumble, drains gurgling, wet urban atmosphere."
        ),
        "light_rain": (
            "Light drizzle on leaves and rooftops, gentle pattering, occasional drip, "
            "fresh petrichor atmosphere, soft and soothing."
        ),
        "crowd": (
            "Busy crowd murmur, overlapping conversations, shuffling footsteps on hard floor, "
            "occasional laughter, ambient public space energy."
        ),
        "traffic": (
            "Urban traffic hum, cars passing, distant horn honks, engine acceleration, "
            "tyre on asphalt, city intersection ambience."
        ),
        "machinery": (
            "Industrial machinery hum, rhythmic mechanical clanking, metal on metal, "
            "ventilation fans, hydraulic hiss, factory floor ambience."
        ),
        "footsteps": (
            "Footsteps on wood floor, rhythmic walking pace, heel and toe, "
            "subtle floor creak, clothing rustle with movement."
        ),
        "footsteps_gravel": (
            "Footsteps crunching on gravel path, each step distinct, "
            "pebbles shifting and scattering, outdoor texture."
        ),
        "room_tone": (
            "Quiet indoor room tone, faint air conditioning hum, "
            "subtle electrical buzz, calm and still, minimal presence."
        ),
        "forest": (
            "Forest ambience, birds chirping in trees, wind through leaves, "
            "distant woodpecker, branches creaking, insects, earthy quiet."
        ),
        "ocean": (
            "Ocean waves rolling in and receding, rhythmic surge, "
            "sea foam hiss, seagulls calling, open coastal air."
        ),
        "wind": (
            "Wind gusting through open space, howling around corners, "
            "rustling fabric and leaves, swaying branches, open air sweep."
        ),
        "fire": (
            "Crackling fire, logs shifting, popping embers, heat shimmer sound, "
            "occasional burst of flame, warm and consuming."
        ),
        "kitchen": (
            "Kitchen ambience, sizzling pan, chopping on cutting board, "
            "running tap water, cabinet doors, plates and utensils."
        ),
        "cafe": (
            "Quiet cafe murmur, espresso machine hiss and clatter, "
            "clinking cups, soft background chatter, chair scrape."
        ),
        "office": (
            "Open office ambience, keyboard typing, mouse clicks, "
            "distant phone, paper shuffle, HVAC hum, calm productivity."
        ),
    }

    return env_prompts.get(
        scene_foley_descriptor.lower().replace(" ", "_"),
        scene_foley_descriptor,
    )


# ---------------------------------------------------------------------------
# Stability AI Stable Audio 2.0 generation
# ---------------------------------------------------------------------------

def generate_stability_foley(
    foley_description: str,
    output_path: str,
    duration: float = 5.0,  # Per-scene foley callers should pass scene_duration (~15-60s); 5.0 is the per-shot default.
    steps: int = 50,
    cfg_scale: float = 7.0,
    seed: int | None = None,
    cost_tracker: "Optional[object]" = None,
) -> str | None:
    """Generate environmental foley via Stability AI Stable Audio 2.0 REST API.

    Caller-controlled caching: if ``output_path`` already exists this
    function returns it immediately without calling the API. The caller
    decides whether to regenerate by removing the file first.

    Args:
        foley_description: text prompt for the sound to generate (use
            ``_build_foley_prompt`` to elaborate a short descriptor)
        output_path: where to save the mp3
        duration: target seconds; capped at 190 per Stability API limit
        steps: diffusion sampling steps (30-100; 50 is the sweet spot)
        cfg_scale: classifier-free guidance scale (1-10; 7.0 default)
        seed: optional reproducibility seed; omitted from form if None

    Returns:
        ``output_path`` on success, ``None`` on missing key / HTTP error /
        any exception. Never raises — graceful degradation.
    """
    # Caller-controlled cache hit
    if os.path.exists(output_path):
        print(f"   [FOLEY] Cache hit: {output_path}")
        return output_path

    api_key = settings.stability_api_key
    if not api_key:
        print("   [FOLEY] STABILITY_API_KEY not set; skipping")
        return None

    try:
        url = "https://api.stability.ai/v2beta/audio/stable-audio-2/text-to-audio"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "audio/*",
        }
        # Stability AI requires multipart form data for this endpoint
        data: dict[str, str] = {
            "prompt": foley_description,
            "duration": str(min(int(round(duration)), 190)),
            "steps": str(steps),
            "cfg_scale": str(cfg_scale),
            "output_format": "mp3",
        }
        if seed is not None:
            data["seed"] = str(seed)

        print(f"   [FOLEY] Generating foley ({duration}s): {foley_description[:80]}...")
        r = requests.post(
            url,
            headers=headers,
            files={k: (None, v) for k, v in data.items()},
            timeout=120,
        )
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)
        print(f"   ✅ Stable Audio Foley saved as: {output_path}")
        # Best-effort cost tracking — M-B2 closure (cycle-16). STABILITY_FOLEY
        # was in API_COST_USD ($0.03) since cycle-15 v0.9.6 but had no
        # record_api_call invocation in production (Lane V ab832c7 confirmed).
        # Mirrors Cartesia pattern at audio/dialogue.py:419-427.
        # T5: use caller-supplied tracker when provided so spend accumulates on
        # the pipeline's budget-aware tracker (cross-process persistence deferred).
        try:
            from cost_tracker import CostTracker
            _tracker = cost_tracker or CostTracker()
            _tracker.record_api_call("STABILITY_FOLEY", operation="scene_foley")
        except Exception:
            print(f"   [FOLEY] cost record skipped (non-critical)")
        return output_path

    except Exception as e:
        print(f"   ⚠️ [FOLEY] failed: {e}")
        return None
