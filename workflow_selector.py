"""
Cinema Production Tool — Workflow Selector (Lightweight ComfyGPT)
Automatically classifies shots by type and selects optimal workflow parameters.

Single quality tier: "production" — pre-tuned params for base pulid.json
(5 templates). The former "max" tier (pulid_max.json: N=8 best-of, 4-layer
identity, 4-channel Union CN, Redux, multi-pass refinement, SUPIR upscale)
was retired WS1 Task 2 (MAX_QUALITY_TEMPLATES/get_max_quality_params) and
WS1 Task 4 (the quality_max.py driver + pulid_max.json graph themselves).

Shot types: portrait, medium, wide, action, landscape
Each type optimizes: PuLID weight, guidance, steps, denoise.
"""

import math
import re
from datetime import date
from typing import Callable, Dict, List, Mapping, Optional

from domain.provider_catalog import RuntimeSnapshot
from domain.video_engine_policy import (
    VideoCandidateResult,
    build_runtime_snapshot,
    resolve_workflow_candidates,
)

# Shot type → optimized parameters
# Based on the paper's recommendation to route tasks to appropriate engines
WORKFLOW_TEMPLATES: Dict[str, Dict] = {
    "portrait": {
        "pulid_weight": 1.0,      # Maximum face-lock for close-ups
        "pulid_start_at": 0.0,    # FLUX: bind from step 0 (coarse-identity window); was SDXL-era 0.2
        "pulid_end_at": 1.0,
        "guidance": 3.5,           # FLUX sweet spot for photorealism + prompt adherence
        "steps": 25,               # More steps = finer skin texture, pore detail, iris sharpness
        "sampler": "dpmpp_2m",     # DPM++ 2M: higher-order solver, sharper at same step count
        "scheduler": "sgm_uniform", # SGM Uniform: optimized sigma distribution for FLUX flow-matching
        "pag_scale": 3.0,          # PAG: sharpen fine face details without oversaturating
        "denoise_default": 0.25,   # Lower denoise = tighter temporal consistency in img2img
        # GEMINI_OMNI = Gemini Omni Flash (Preview), Google-first primary since
        # WS2 (Gemini Omni Flash is arena #1). KLING_3_0 = fal Kling v3 Pro
        # (#11 AA i2v arena, 2026-07-11) with `elements` identity binding stays
        # first non-Google fallback. The deprecated native kling-v1-6 adapter
        # is quarantined from automatic routing and remains explicit-only.
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "KLING_3_0", "RUNWAY_GEN4", "SEEDANCE"],
        "description": "Close-up portrait — max face fidelity, 25 steps, DPM++ 2M + PAG",
    },
    "medium": {
        "pulid_weight": 0.9,
        "pulid_start_at": 0.0,    # FLUX: bind from step 0 (was SDXL-era 0.25)
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Matched to portrait — consistent look across shot types
        "steps": 20,                # Up from 15 — visible quality jump for mid-range detail
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 3.0,          # PAG: enhance mid-range detail (clothing, background texture)
        "denoise_default": 0.35,
        # GEMINI_OMNI Google-first primary (WS2); fal Kling v3 Pro (elements
        # identity) first non-Google fallback; native v1.6 is explicit-only.
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "KLING_3_0", "RUNWAY_GEN4", "SEEDANCE", "LTX"],
        "description": "Medium shot — balanced face + scene, 20 steps, DPM++ 2M + PAG",
    },
    "wide": {
        "pulid_weight": 0.65,      # Slightly lower — face is small, environment matters more
        "pulid_start_at": 0.0,    # FLUX: bind from step 0 (was SDXL-era 0.35)
        "pulid_end_at": 0.9,       # End at 90% — final 10% for environment polish without face interference
        "guidance": 3.0,            # Moderate guidance — balance prompt and creative freedom
        "steps": 20,                # Up from 12 — wide shots need detail for background architecture
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 2.5,          # Lower PAG — avoid over-sharpening large environments
        "denoise_default": 0.45,
        # GEMINI_OMNI Google-first primary (WS2); old target_api LTX demoted
        # into 2nd fallback slot; old VEO_NATIVE fallback deduped (now the head).
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "LTX", "KLING_3_0", "RUNWAY_GEN4"],
        "description": "Wide establishing shot — environment-first, 20 steps, DPM++ 2M + PAG",
    },
    "action": {
        "pulid_weight": 0.8,       # Slightly reduced — action poses stress face-lock
        "pulid_start_at": 0.0,     # FLUX: bind from step 0 (was SDXL-era 0.3)
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Higher guidance for action = tighter prompt control of motion
        "steps": 20,                # Consistent step count across all character shots
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 2.0,          # Lower PAG — motion shots need softness, not crispness
        "denoise_default": 0.40,
        # GEMINI_OMNI Google-first primary (WS2). SEEDANCE (#1 AA i2v arena,
        # 2026-07; multi-reference up to 9 images binds multi-character action)
        # demoted into 2nd fallback slot. Deprecated SORA_NATIVE remains
        # available only when an operator explicitly pins it before sunset;
        # new automatic action routing must not introduce it.
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "SEEDANCE", "KLING_3_0", "RUNWAY_GEN4", "LTX"],
        "description": "Action/movement — motion-stable, 20 steps, DPM++ 2M + PAG",
    },
    "landscape": {
        "pulid_weight": 0.0,       # NO face-lock — no characters in frame
        "pulid_start_at": 0.0,
        "pulid_end_at": 0.0,
        "guidance": 4.0,            # Higher guidance for landscapes = sharper architectural detail
        "steps": 25,                # Max steps — environment shots benefit most from detail refinement
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 3.5,          # Max PAG — landscapes benefit most from detail sharpening
        "denoise_default": 0.55,
        # GEMINI_OMNI Google-first primary (WS2); old target_api LTX demoted;
        # old VEO_NATIVE fallback deduped (now the head).
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "LTX", "KLING_3_0"],
        "description": "Pure landscape — no PuLID, 25 steps, max detail + PAG",
    },
    # NOTE: "dialogue" is not a ComfyUI image-gen template — dialogue shots use
    # portrait/medium templates for image generation, then the controller picks
    # the first policy-admitted native-audio video route. Any result without
    # verified embedded dialogue traverses the separate F1b lip-sync cascade.
    # Assembly uses HARD CUTS only — no AI-generated transition clips.
}

# Keywords for classification — order matters (first match wins)
SHOT_TYPE_KEYWORDS = {
    "portrait": [
        "close-up", "closeup", "close up", "portrait", "ecu", "extreme close",
        "85mm", "macro", "headshot", "face shot", "tight shot",
    ],
    "action": [
        "tracking", "tracking shot", "crane", "dolly", "rapid", "chase",
        "running", "action", "dynamic", "handheld", "steadicam",
    ],
    "wide": [
        "wide shot", "wide angle", "establishing", "24mm", "16mm",
        "full shot", "long shot", "master shot", "extreme wide",
    ],
    "landscape": [
        "landscape", "aerial", "drone", "skyline", "panoramic",
        "environment", "scenery", "no character",
    ],
    "medium": [
        "medium", "50mm", "mid-shot", "waist", "hip", "american shot",
        "cowboy shot", "two-shot",
    ],
}


# =============================================================================
# MOTION-FIDELITY FLOORS — per-shot-type advisory thresholds
# =============================================================================
# Advisory only — never auto-fail a take per operator decision (handoff §3.4).
# These values are used exclusively for logging, UI warnings, and diagnostics.
# No gate, no hard reject, no automatic re-roll should reference this dict.
#
# TODO(calibrate): Placeholders below are starting points from plan §3.2.
# They MUST be replaced with operator-calibrated values derived from a 20-shot
# grading pass before these floors carry any production meaning.
# See scripts/calibrate_motion_floor.py for the calibration workflow.
MOTION_FIDELITY_FLOORS: Dict[str, Optional[float]] = {
    "portrait":  0.42,
    "medium":    0.55,
    "wide":      0.65,
    "action":    0.60,
    "landscape": None,   # Motion capture doesn't apply to pure landscape shots
}


def get_motion_fidelity_floor(shot_type: str) -> Optional[float]:
    """Return the motion-fidelity floor for a shot type, or None when motion
    capture doesn't apply (landscapes)."""
    return MOTION_FIDELITY_FLOORS.get(shot_type)


def classify_shot_type(shot: dict) -> str:
    """
    Classify a shot into one of 5 types based on its prompt content
    and character presence.

    Priority:
    1. If no characters in frame → landscape
    2. Parse [SHOT] section for keywords
    3. Parse full prompt for keywords
    4. Default → medium (safest fallback)

    Returns: "portrait" | "medium" | "wide" | "action" | "landscape"
    """
    chars = shot.get("characters_in_frame", [])
    prompt = shot.get("prompt", "").lower()
    camera = shot.get("camera", "").lower()

    # No characters → landscape
    if not chars:
        return "landscape"

    # Extract [SHOT] section if structured
    shot_section = ""
    match = re.search(r'\[SHOT\]\s*(.+?)(?=\[(?:SCENE|ACTION|OUTFIT|QUALITY)\]|$)', prompt, re.DOTALL)
    if match:
        shot_section = match.group(1).lower().strip()

    # Check keywords — search in shot section first, then full prompt + camera
    search_text = f"{shot_section} {prompt} {camera}"

    for shot_type, keywords in SHOT_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in search_text:
                # A landscape-keyword shot that STILL has a registered character
                # must keep identity: route to "wide" (pulid_weight 0.65 in both
                # tiers) rather than "landscape" (production drops the reference;
                # max zeroes the weight). The characterless case already returned
                # "landscape" via the early-return above, so this only overrides
                # char-BEARING landscapes. (ADR-025 scope-exemption close.)
                if shot_type == "landscape" and chars:
                    return "wide"
                return shot_type

    # Default to medium (safest — decent face-lock + scene balance)
    return "medium"


def get_resolved_workflow_routing(
    shot_type: str,
    *,
    settings: Optional[dict] = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
    module_probe: Callable[[str], bool] | None = None,
) -> VideoCandidateResult:
    """Resolve a historical template's video order through typed policy.

    ``WORKFLOW_TEMPLATES`` remains the compatibility/order seed.  This accessor
    is the executable view: it preserves order, removes duplicates, records
    rejection evidence, honors an explicit project ``enabled: false``, and
    yields ``primary == "AUTO"`` when no concrete engine is currently ready.
    """

    template = WORKFLOW_TEMPLATES.get(
        shot_type,
        WORKFLOW_TEMPLATES["medium"],
    )
    api_engines: Mapping[str, object] | None = None
    if isinstance(settings, Mapping):
        configured_engines = settings.get("api_engines")
        if isinstance(configured_engines, Mapping):
            api_engines = configured_engines
    snapshot = (
        runtime_snapshot
        if runtime_snapshot is not None
        else build_runtime_snapshot(module_probe=module_probe)
    )
    return resolve_workflow_candidates(
        template.get("target_api", "AUTO"),
        template.get("video_fallbacks", ()),
        snapshot=snapshot,
        on_date=on_date,
        api_engines=api_engines,
    )


def get_workflow_params(
    shot_type: str,
    quality_tier: str = "production",
    settings: Optional[dict] = None,
    *,
    runtime_snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
    module_probe: Callable[[str], bool] | None = None,
) -> Dict:
    """Get the optimized workflow parameters for a shot type.

    Args:
        shot_type: "portrait" | "medium" | "wide" | "action" | "landscape"
        quality_tier: retained for signature compat only — production (pulid.json)
            is the sole tier now that MAX_QUALITY_TEMPLATES/get_max_quality_params
            have been retired (WS1 Task 2). No longer branches on this value.
        settings: Optional project settings dict (ctx.global_settings or equivalent).
            When provided, overlays the 4 per-project UI knobs onto the returned params:
              flux_guidance    → guidance   (float)
              comfyui_sampler  → sampler    (str)
              comfyui_steps    → steps      (int)
              comfyui_upscale  → (skipped — no "upscale" key in production templates)

    Returns: copy of the matching template dict (callers may mutate freely).
    """
    params = WORKFLOW_TEMPLATES.get(shot_type, WORKFLOW_TEMPLATES["medium"]).copy()
    routing = get_resolved_workflow_routing(
        shot_type,
        settings=settings,
        runtime_snapshot=runtime_snapshot,
        on_date=on_date,
        module_probe=module_probe,
    )
    params["target_api"] = routing.primary
    params["video_fallbacks"] = list(routing.fallbacks)

    if settings:
        # Per-project UI overrides — overlay only EXISTING param-dict keys.
        # Note: comfyui_upscale is intentionally omitted; no "upscale" key exists
        # in WORKFLOW_TEMPLATES, so we don't invent one here.
        flux_guidance = settings.get("flux_guidance")
        if (flux_guidance is not None and isinstance(flux_guidance, (int, float))
                and math.isfinite(flux_guidance)):
            # math.isfinite: a NaN/inf flux_guidance (survives project.json via
            # json.load allow_nan) would inject a non-finite into FluxGuidance
            # node 60 -> silent generation corruption. Skip -> template default.
            params["guidance"] = float(flux_guidance)

        comfyui_sampler = settings.get("comfyui_sampler")
        if comfyui_sampler is not None and isinstance(comfyui_sampler, str):
            params["sampler"] = comfyui_sampler

        comfyui_steps = settings.get("comfyui_steps")
        if (comfyui_steps is not None and isinstance(comfyui_steps, (int, float))
                and math.isfinite(comfyui_steps)):
            # math.isfinite BEFORE int(): int(float('nan')) raises ValueError and
            # int(float('inf')) raises OverflowError — a non-finite comfyui_steps
            # would crash param resolution instead of skipping the bad knob.
            params["steps"] = int(comfyui_steps)

        # img2img_denoise is nested under continuity_options (unlike the top-level
        # knobs above).  Validate in-range [0.2, 0.6] matching the slider bounds
        # in web_server.py:331 before writing — the JSON API can send any float.
        # isinstance(_co, dict): a present-but-null continuity_options (JSON null)
        # makes settings.get(..., {}) return None (the {} default applies only to a
        # MISSING key), so None.get('img2img_denoise') raises AttributeError. (bf1034a
        # closed the main non-finite issue but its audit boundary missed this sibling;
        # the quality_max.py sibling site that used to mirror this guard was retired
        # WS1 Task 4.)
        _co = settings.get("continuity_options", {})
        img2img_denoise = _co.get("img2img_denoise") if isinstance(_co, dict) else None
        if (img2img_denoise is not None and isinstance(img2img_denoise, (int, float))
                and math.isfinite(img2img_denoise)):
            # math.isfinite: the [0.2,0.6] clamp neutralises non-finite by luck
            # (nan->0.6), silently overwriting the template default. Skip instead
            # (formerly matched quality_max._clamp_img2img_denoise's reject-non-finite
            # policy; that module was retired WS1 Task 4).
            clamped = max(0.2, min(0.6, float(img2img_denoise)))
            params["denoise_default"] = clamped

    return params


def apply_workflow_params(workflow: dict, params: Dict) -> dict:
    """
    Apply shot-type-specific parameters to a ComfyUI workflow JSON.
    Modifies the workflow IN PLACE and returns it.

    Node map:
    - Node 100 (ApplyPulidFlux): weight, start_at, end_at (fusion is graph default "mean")
    - Node 60 (FluxGuidance): guidance
    - Node 17 (BasicScheduler): steps, denoise, scheduler
    - Node 16 (KSamplerSelect): sampler_name
    - Node 301 (PAG): detail enhancement scale
    """
    # PuLID face-lock parameters (Node 100)
    if "100" in workflow:
        workflow["100"]["inputs"]["weight"] = params.get("pulid_weight", 1.0)
        workflow["100"]["inputs"]["start_at"] = params.get("pulid_start_at", 0.0)
        workflow["100"]["inputs"]["end_at"] = params.get("pulid_end_at", 1.0)

    # Guidance / CFG (Node 60)
    if "60" in workflow:
        workflow["60"]["inputs"]["guidance"] = params.get("guidance", 3.5)

    # Steps + scheduler (Node 17)
    if "17" in workflow:
        workflow["17"]["inputs"]["steps"] = params.get("steps", 20)
        workflow["17"]["inputs"]["scheduler"] = params.get("scheduler", "sgm_uniform")
        # Don't override denoise here — it's set by img2img logic in generate_ai_broll

    # Sampler algorithm (Node 16)
    if "16" in workflow:
        workflow["16"]["inputs"]["sampler_name"] = params.get("sampler", "dpmpp_2m")

    # PAG detail enhancement (Node 301)
    if "301" in workflow:
        workflow["301"]["inputs"]["scale"] = params.get("pag_scale", 3.0)

    return workflow


def get_adaptive_pulid_weight(
    shot_type: str,
    character_id: str,
    identity_validator,
    base_params: Dict = None,
    settings: Optional[dict] = None,
) -> float:
    """
    Compute adaptive PuLID weight based on rolling identity performance.

    Feedback loop:
    - Identity keeps failing → validator suggests +0.10 → PuLID weight increases
    - Identity consistently passing high → validator suggests -0.05 → more creative freedom
    - Smart: doesn't boost PuLID for FACE_ANGLE_EXTREME or SMALL_FACE_REGION
    """
    if base_params is None:
        base_params = get_workflow_params(shot_type, settings=settings)

    base_weight = base_params.get("pulid_weight", 0.9)

    if identity_validator is None:
        return base_weight

    stats = identity_validator.get_rolling_stats(character_id)
    if stats.get("sample_count", 0) == 0:
        return base_weight

    delta = stats.get("suggested_pulid_delta", 0.0)

    # Don't boost PuLID for failures it can't fix
    from identity.types import FailureReason
    common_failure = stats.get("common_failure")
    if common_failure == FailureReason.FACE_ANGLE_EXTREME:
        delta = min(delta, 0.0)
    elif common_failure == FailureReason.SMALL_FACE_REGION:
        delta = 0.0

    adapted = max(0.0, min(1.0, base_weight + delta))
    if abs(delta) > 0.01:
        print(f"      [ADAPTIVE] PuLID weight for {character_id}: {base_weight} → {adapted:.2f} (delta={delta:+.2f})")
    return adapted
