"""
Cinema Production Tool — Workflow Selector (Lightweight ComfyGPT)
Automatically classifies shots by type and selects optimal workflow parameters.

Two quality tiers:
  - "production" (default): pre-tuned params for base pulid.json (5 templates)
  - "max":                  full maxed stack for pulid_max.json (N=8 best-of,
                            4-layer identity, 4-channel Union CN, Redux,
                            multi-pass refinement, SUPIR upscale)

Shot types: portrait, medium, wide, action, landscape
Each type optimizes: PuLID weight, guidance, steps, denoise — and at max tier
also: SLG/FreeU scales, CN channel strengths, DetailDaemon, halt rules.
"""

import re
from typing import Dict, List, Optional

# Shot type → optimized parameters
# Based on the paper's recommendation to route tasks to appropriate engines
WORKFLOW_TEMPLATES: Dict[str, Dict] = {
    "portrait": {
        "pulid_weight": 1.0,      # Maximum face-lock for close-ups
        "pulid_start_at": 0.2,    # Face influence from 20% — earlier = stronger identity bake-in
        "pulid_end_at": 1.0,
        "guidance": 3.5,           # FLUX sweet spot for photorealism + prompt adherence
        "steps": 25,               # More steps = finer skin texture, pore detail, iris sharpness
        "sampler": "dpmpp_2m",     # DPM++ 2M: higher-order solver, sharper at same step count
        "scheduler": "sgm_uniform", # SGM Uniform: optimized sigma distribution for FLUX flow-matching
        "pag_scale": 3.0,          # PAG: sharpen fine face details without oversaturating
        "controlnet_depth_strength": 0.35,  # Subtle spatial lock from previous shot
        "ip_adapter_weight": 0.25, # Minimal style transfer — face is priority
        "denoise_default": 0.25,   # Lower denoise = tighter temporal consistency in img2img
        "target_api": "KLING_NATIVE",  # Best face: subject binding + face_consistency
        "video_fallbacks": ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_3_0"],
        "description": "Close-up portrait — max face fidelity, 25 steps, DPM++ 2M + PAG",
    },
    "medium": {
        "pulid_weight": 0.9,
        "pulid_start_at": 0.25,    # Earlier start than before for stronger face hold
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Matched to portrait — consistent look across shot types
        "steps": 20,                # Up from 15 — visible quality jump for mid-range detail
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 3.0,          # PAG: enhance mid-range detail (clothing, background texture)
        "controlnet_depth_strength": 0.40,  # Moderate spatial lock
        "ip_adapter_weight": 0.30, # Balanced style transfer
        "denoise_default": 0.35,
        "target_api": "KLING_NATIVE",  # Good face + scene balance
        "video_fallbacks": ["RUNWAY_GEN4", "SORA_NATIVE", "LTX"],
        "description": "Medium shot — balanced face + scene, 20 steps, DPM++ 2M + PAG",
    },
    "wide": {
        "pulid_weight": 0.65,      # Slightly lower — face is small, environment matters more
        "pulid_start_at": 0.35,    # Later start — let environment establish first
        "pulid_end_at": 0.9,       # End at 90% — final 10% for environment polish without face interference
        "guidance": 3.0,            # Moderate guidance — balance prompt and creative freedom
        "steps": 20,                # Up from 12 — wide shots need detail for background architecture
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 2.5,          # Lower PAG — avoid over-sharpening large environments
        "controlnet_depth_strength": 0.50,  # Strongest spatial lock — wide shots drift most
        "ip_adapter_weight": 0.35, # Higher style transfer — lock environment atmosphere
        "denoise_default": 0.45,
        "target_api": "LTX",            # 4K, 3D camera, depth-aware, cheapest
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE", "RUNWAY_GEN4"],
        "description": "Wide establishing shot — environment-first, 20 steps, DPM++ 2M + PAG",
    },
    "action": {
        "pulid_weight": 0.8,       # Slightly reduced — action poses stress face-lock
        "pulid_start_at": 0.3,     # Balanced start — face needs to hold through motion
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Higher guidance for action = tighter prompt control of motion
        "steps": 20,                # Consistent step count across all character shots
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 2.0,          # Lower PAG — motion shots need softness, not crispness
        "controlnet_depth_strength": 0.30,  # Light spatial guidance — allow motion freedom
        "ip_adapter_weight": 0.25, # Light style transfer — don't constrain action
        "denoise_default": 0.40,
        "target_api": "SORA_NATIVE",    # Best motion physics, body momentum, cloth sim
        # SEEDANCE last — its multi-reference (up to 9 images) is the only
        # cascade member that handles multi-character action shots well.
        "video_fallbacks": ["KLING_NATIVE", "RUNWAY_GEN4", "LTX", "SEEDANCE"],
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
        "controlnet_depth_strength": 0.55,  # Strong spatial lock for architecture/layout
        "ip_adapter_weight": 0.40, # Max style transfer — lock atmosphere and color grade
        "denoise_default": 0.55,
        "target_api": "LTX",            # 4K, no face needed, cheapest, best environments
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE"],
        "description": "Pure landscape — no PuLID, 25 steps, max detail + PAG",
    },
    # NOTE: "dialogue" is not a ComfyUI image-gen template — dialogue shots use
    # portrait/medium templates for image generation, then the pipeline routes
    # to a video API with native lipsync.
    # The video generation cascade for dialogue: VEO_NATIVE → Kling Lip Sync → Omnihuman.
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
# MAX-QUALITY TIER — for pulid_max.json (full maxed stack)
# =============================================================================
# Per-shot-type tuning for the max graph. Every shot type gets the SAME
# generation budget (N=8) but the halt threshold and the conditioning mix
# vary. Values here are deliberately bolder than the production tier — this
# is the "ignore cost, max quality" path.
MAX_QUALITY_TEMPLATES: Dict[str, Dict] = {
    "portrait": {
        "candidate_count": 8,
        "candidate_batch": 4,
        "halt_threshold_composite": 0.92,
        "halt_threshold_arc": 0.85,
        "halt_min_n": 4,
        "regenerate_floor_arc": 0.82,
        "pulid_weight": 0.85,
        "pulid_start_at": 0.0,
        "pulid_end_at": 0.90,
        "lora_strength_model": 1.0,
        "lora_strength_clip": 1.0,
        "guidance": 3.5,
        "ays_steps": 28,
        "sampler": "dpmpp_3m_sde_gpu",
        "scheduler_ays": True,
        "pag_scale": 3.0,
        "slg_scale": 2.5,
        "slg_double_layers": "7,8,9",
        "slg_single_layers": "10,11",
        "freeu_b1": 1.3, "freeu_b2": 1.4, "freeu_s1": 0.9, "freeu_s2": 0.2,
        "detail_daemon_amount": 0.5,
        "diffdiff_enabled": True,
        "cn_depth_strength": 0.40,
        "cn_canny_strength": 0.15,
        "cn_pose_strength": 0.35,
        "cn_tile_strength": 0.25,
        "redux_strength": "high",
        "redux_end_at": 0.50,
        "latent_blend_ratio": 0.15,
        "hires_fix_enabled": True,
        "hires_fix_scale": 1.5,
        "hires_fix_denoise": 0.40,
        "hires_fix_steps": 18,
        "face_detailer_enabled": True,
        "face_detailer_guide_size": 1024,
        "face_detailer_denoise": 0.35,
        "supir_enabled": True,
        "supir_steps": 50,
        "supir_cfg_scale": 4.0,
        "final_resolution": (3840, 2160),
        "target_api": "KLING_NATIVE",
        "video_fallbacks": ["RUNWAY_GEN4", "SORA_NATIVE", "VEO_NATIVE"],
        "description": "MAX portrait — 4-layer identity, full CN+Redux, N=8 halt@0.92, all post-passes",
    },
    "medium": {
        "candidate_count": 8,
        "candidate_batch": 4,
        "halt_threshold_composite": 0.90,
        "halt_threshold_arc": 0.83,
        "halt_min_n": 4,
        "regenerate_floor_arc": 0.80,
        "pulid_weight": 0.80,
        "pulid_start_at": 0.0,
        "pulid_end_at": 0.90,
        "lora_strength_model": 1.0,
        "lora_strength_clip": 1.0,
        "guidance": 3.5,
        "ays_steps": 28,
        "sampler": "dpmpp_3m_sde_gpu",
        "scheduler_ays": True,
        "pag_scale": 3.0,
        "slg_scale": 2.5,
        "slg_double_layers": "7,8,9",
        "slg_single_layers": "10,11",
        "freeu_b1": 1.3, "freeu_b2": 1.4, "freeu_s1": 0.9, "freeu_s2": 0.2,
        "detail_daemon_amount": 0.45,
        "diffdiff_enabled": True,
        "cn_depth_strength": 0.42,
        "cn_canny_strength": 0.15,
        "cn_pose_strength": 0.32,
        "cn_tile_strength": 0.25,
        "redux_strength": "high",
        "redux_end_at": 0.50,
        "latent_blend_ratio": 0.15,
        "hires_fix_enabled": True,
        "hires_fix_scale": 1.5,
        "hires_fix_denoise": 0.40,
        "hires_fix_steps": 18,
        "face_detailer_enabled": True,
        "face_detailer_guide_size": 1024,
        "face_detailer_denoise": 0.35,
        "supir_enabled": True,
        "supir_steps": 50,
        "supir_cfg_scale": 4.0,
        "final_resolution": (3840, 2160),
        "target_api": "KLING_NATIVE",
        "video_fallbacks": ["RUNWAY_GEN4", "SORA_NATIVE", "LTX"],
        "description": "MAX medium — same identity stack, slightly relaxed thresholds",
    },
    "wide": {
        "candidate_count": 8,
        "candidate_batch": 4,
        "halt_threshold_composite": 0.88,
        "halt_threshold_arc": 0.78,
        "halt_min_n": 4,
        "regenerate_floor_arc": 0.72,
        "pulid_weight": 0.65,
        "pulid_start_at": 0.20,
        "pulid_end_at": 0.85,
        "lora_strength_model": 0.9,
        "lora_strength_clip": 0.9,
        "guidance": 3.5,
        "ays_steps": 28,
        "sampler": "dpmpp_3m_sde_gpu",
        "scheduler_ays": True,
        "pag_scale": 2.8,
        "slg_scale": 2.5,
        "slg_double_layers": "7,8,9",
        "slg_single_layers": "10,11",
        "freeu_b1": 1.3, "freeu_b2": 1.4, "freeu_s1": 0.9, "freeu_s2": 0.2,
        "detail_daemon_amount": 0.5,
        "diffdiff_enabled": True,
        "cn_depth_strength": 0.50,
        "cn_canny_strength": 0.18,
        "cn_pose_strength": 0.25,
        "cn_tile_strength": 0.30,
        "redux_strength": "high",
        "redux_end_at": 0.50,
        "latent_blend_ratio": 0.18,
        "hires_fix_enabled": True,
        "hires_fix_scale": 1.5,
        "hires_fix_denoise": 0.42,
        "hires_fix_steps": 18,
        "face_detailer_enabled": False,
        "face_detailer_guide_size": 1024,
        "face_detailer_denoise": 0.35,
        "supir_enabled": True,
        "supir_steps": 50,
        "supir_cfg_scale": 4.0,
        "final_resolution": (3840, 2160),
        "target_api": "LTX",
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE", "RUNWAY_GEN4"],
        "description": "MAX wide — face too small for FaceDetailer; CN spatial dominant",
    },
    "action": {
        "candidate_count": 8,
        "candidate_batch": 4,
        "halt_threshold_composite": 0.88,
        "halt_threshold_arc": 0.80,
        "halt_min_n": 4,
        "regenerate_floor_arc": 0.75,
        "pulid_weight": 0.75,
        "pulid_start_at": 0.0,
        "pulid_end_at": 0.90,
        "lora_strength_model": 1.0,
        "lora_strength_clip": 1.0,
        "guidance": 3.5,
        "ays_steps": 28,
        "sampler": "dpmpp_3m_sde_gpu",
        "scheduler_ays": True,
        "pag_scale": 2.5,
        "slg_scale": 2.0,
        "slg_double_layers": "7,8,9",
        "slg_single_layers": "10,11",
        "freeu_b1": 1.2, "freeu_b2": 1.3, "freeu_s1": 0.9, "freeu_s2": 0.2,
        "detail_daemon_amount": 0.4,
        "diffdiff_enabled": True,
        "cn_depth_strength": 0.32,
        "cn_canny_strength": 0.12,
        "cn_pose_strength": 0.28,
        "cn_tile_strength": 0.20,
        "redux_strength": "medium",
        "redux_end_at": 0.45,
        "latent_blend_ratio": 0.12,
        "hires_fix_enabled": True,
        "hires_fix_scale": 1.5,
        "hires_fix_denoise": 0.45,
        "hires_fix_steps": 18,
        "face_detailer_enabled": True,
        "face_detailer_guide_size": 1024,
        "face_detailer_denoise": 0.35,
        "supir_enabled": True,
        "supir_steps": 50,
        "supir_cfg_scale": 4.0,
        "final_resolution": (3840, 2160),
        "target_api": "SORA_NATIVE",
        # SEEDANCE last — multi-reference fallback for multi-character action.
        "video_fallbacks": ["KLING_NATIVE", "RUNWAY_GEN4", "LTX", "SEEDANCE"],
        "description": "MAX action — softer guidance for motion, lower CN strength to allow movement",
    },
    "landscape": {
        "candidate_count": 8,
        "candidate_batch": 4,
        "halt_threshold_composite": 0.90,
        "halt_threshold_arc": 0.0,
        "halt_min_n": 4,
        "regenerate_floor_arc": 0.0,
        "pulid_weight": 0.0,
        "pulid_start_at": 0.0,
        "pulid_end_at": 0.0,
        "lora_strength_model": 0.0,
        "lora_strength_clip": 0.0,
        "guidance": 4.0,
        "ays_steps": 30,
        "sampler": "dpmpp_3m_sde_gpu",
        "scheduler_ays": True,
        "pag_scale": 3.5,
        "slg_scale": 2.8,
        "slg_double_layers": "7,8,9",
        "slg_single_layers": "10,11",
        "freeu_b1": 1.3, "freeu_b2": 1.4, "freeu_s1": 0.9, "freeu_s2": 0.2,
        "detail_daemon_amount": 0.6,
        "diffdiff_enabled": True,
        "cn_depth_strength": 0.55,
        "cn_canny_strength": 0.20,
        "cn_pose_strength": 0.0,
        "cn_tile_strength": 0.35,
        "redux_strength": "high",
        "redux_end_at": 0.55,
        "latent_blend_ratio": 0.20,
        "hires_fix_enabled": True,
        "hires_fix_scale": 1.5,
        "hires_fix_denoise": 0.45,
        "hires_fix_steps": 20,
        "face_detailer_enabled": False,
        "face_detailer_guide_size": 1024,
        "face_detailer_denoise": 0.35,
        "supir_enabled": True,
        "supir_steps": 50,
        "supir_cfg_scale": 4.0,
        "final_resolution": (3840, 2160),
        "target_api": "LTX",
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE"],
        "description": "MAX landscape — no identity stack, max CN + PAG + SLG for architecture/atmosphere",
    },
}


def get_max_quality_params(shot_type: str) -> Dict:
    """Return the maxed parameter template for a shot type.

    Keys cover: candidate budget (N), halt thresholds, identity stack weights,
    ControlNet channel strengths, guidance enhancers, post-pass toggles.
    Consumed by quality_max.generate_ai_broll_max — not used in the production
    tier path.
    """
    return MAX_QUALITY_TEMPLATES.get(shot_type, MAX_QUALITY_TEMPLATES["medium"]).copy()


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
    "macro":     0.40,
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
                return shot_type

    # Default to medium (safest — decent face-lock + scene balance)
    return "medium"


def get_workflow_params(
    shot_type: str,
    quality_tier: str = "production",
    settings: Optional[dict] = None,
) -> Dict:
    """Get the optimized workflow parameters for a shot type and quality tier.

    Args:
        shot_type: "portrait" | "medium" | "wide" | "action" | "landscape"
        quality_tier: "production" (default, pulid.json) or "max" (pulid_max.json).
            Existing callers pass shot_type only and get production behavior unchanged.
        settings: Optional project settings dict (ctx.global_settings or equivalent).
            When provided, overlays the 4 per-project UI knobs onto the returned params:
              flux_guidance    → guidance   (float)
              comfyui_sampler  → sampler    (str)
              comfyui_steps    → steps      (int)
              comfyui_upscale  → (skipped — no "upscale" key in production templates)

    Returns: copy of the matching template dict (callers may mutate freely).
    """
    if quality_tier == "max":
        return get_max_quality_params(shot_type)
    params = WORKFLOW_TEMPLATES.get(shot_type, WORKFLOW_TEMPLATES["medium"]).copy()

    if settings:
        # Per-project UI overrides — overlay only EXISTING param-dict keys.
        # Note: comfyui_upscale is intentionally omitted; no "upscale" key exists
        # in WORKFLOW_TEMPLATES, so we don't invent one here.
        flux_guidance = settings.get("flux_guidance")
        if flux_guidance is not None and isinstance(flux_guidance, (int, float)):
            params["guidance"] = float(flux_guidance)

        comfyui_sampler = settings.get("comfyui_sampler")
        if comfyui_sampler is not None and isinstance(comfyui_sampler, str):
            params["sampler"] = comfyui_sampler

        comfyui_steps = settings.get("comfyui_steps")
        if comfyui_steps is not None and isinstance(comfyui_steps, (int, float)):
            params["steps"] = int(comfyui_steps)

    return params


def apply_workflow_params(workflow: dict, params: Dict) -> dict:
    """
    Apply shot-type-specific parameters to a ComfyUI workflow JSON.
    Modifies the workflow IN PLACE and returns it.

    Node map:
    - Node 100 (ApplyPulid): weight, start_at, end_at, method
    - Node 60 (FluxGuidance): guidance
    - Node 17 (BasicScheduler): steps, denoise, scheduler
    - Node 16 (KSamplerSelect): sampler_name
    - Node 301 (PAG): detail enhancement scale
    """
    # PuLID face-lock parameters (Node 100)
    if "100" in workflow:
        workflow["100"]["inputs"]["weight"] = params.get("pulid_weight", 1.0)
        workflow["100"]["inputs"]["start_at"] = params.get("pulid_start_at", 0.3)
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

