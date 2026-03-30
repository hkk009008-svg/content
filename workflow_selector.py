"""
Cinema Production Tool — Workflow Selector (Lightweight ComfyGPT)
Automatically classifies shots by type and selects optimal workflow parameters.

Instead of generating entire ComfyUI graphs from scratch (full ComfyGPT),
this uses 5 pre-tuned parameter templates applied to the base Pulid.json.

Shot types: portrait, medium, wide, action, landscape
Each type optimizes: PuLID weight, guidance, steps, denoise for maximum quality.
"""

import re
from typing import Dict, List, Optional

from quality_tracker import QualityTracker

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
        "denoise_default": 0.30,   # Tuned: 0.25→0.30 — sweep shows 0.30 optimal consistency/creativity balance for portraits
        "target_api": "KLING_NATIVE",  # Best face: subject binding + face_consistency
        "video_fallbacks": ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_3_0"],
        "description": "Close-up portrait — max face fidelity, 25 steps, DPM++ 2M + PAG",
    },
    "medium": {
        "pulid_weight": 0.85,      # Tuned: 0.9→0.85 — sweep shows diminishing returns above 0.85 for medium shots
        "pulid_start_at": 0.25,    # Earlier start than before for stronger face hold
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Matched to portrait — consistent look across shot types
        "steps": 20,                # Up from 15 — visible quality jump for mid-range detail
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 3.0,          # PAG: enhance mid-range detail (clothing, background texture)
        "controlnet_depth_strength": 0.40,  # Moderate spatial lock
        "ip_adapter_weight": 0.30, # Balanced style transfer
        "denoise_default": 0.35,   # Already at sweep sweet spot (0.35 = best composite 0.6627)
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
        "controlnet_depth_strength": 0.45,  # Tuned: 0.50→0.45 — sweep shows 0.40-0.50 range optimal, slight reduction prevents over-constraining
        "ip_adapter_weight": 0.35, # Higher style transfer — lock environment atmosphere
        "denoise_default": 0.40,   # Tuned: 0.45→0.40 — closer to sweep sweet spot, better consistency without losing scene variation
        "target_api": "LTX",            # 4K, 3D camera, depth-aware, cheapest
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE", "RUNWAY_GEN4"],
        "description": "Wide establishing shot — environment-first, 20 steps, DPM++ 2M + PAG",
    },
    "action": {
        "pulid_weight": 0.75,      # Tuned: 0.8→0.75 — sweep shows lower PuLID reduces motion artifacts in action poses
        "pulid_start_at": 0.3,     # Balanced start — face needs to hold through motion
        "pulid_end_at": 1.0,
        "guidance": 3.5,            # Higher guidance for action = tighter prompt control of motion
        "steps": 20,                # Consistent step count across all character shots
        "sampler": "dpmpp_2m",
        "scheduler": "sgm_uniform",
        "pag_scale": 2.0,          # Lower PAG — motion shots need softness, not crispness
        "controlnet_depth_strength": 0.30,  # Light spatial guidance — allow motion freedom
        "ip_adapter_weight": 0.25, # Light style transfer — don't constrain action
        "denoise_default": 0.35,   # Tuned: 0.40→0.35 — sweep sweet spot, best composite score
        "target_api": "SORA_NATIVE",    # Best motion physics, body momentum, cloth sim
        "video_fallbacks": ["KLING_NATIVE", "RUNWAY_GEN4", "LTX"],
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
        "controlnet_depth_strength": 0.50,  # Tuned: 0.55→0.50 — sweep shows 0.50 sufficient, reduces over-constraining
        "ip_adapter_weight": 0.40, # Max style transfer — lock atmosphere and color grade
        "denoise_default": 0.50,   # Tuned: 0.55→0.50 — sweet spot between consistency (0.61) and creativity (0.50)
        "target_api": "LTX",            # 4K, no face needed, cheapest, best environments
        "video_fallbacks": ["VEO_NATIVE", "KLING_NATIVE"],
        "description": "Pure landscape — no PuLID, 25 steps, max detail + PAG",
    },
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


def get_workflow_params(shot_type: str) -> Dict:
    """Get the optimized workflow parameters for a shot type."""
    return WORKFLOW_TEMPLATES.get(shot_type, WORKFLOW_TEMPLATES["medium"]).copy()


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
) -> float:
    """
    Compute adaptive PuLID weight based on rolling identity performance.

    Feedback loop:
    - Identity keeps failing → validator suggests +0.10 → PuLID weight increases
    - Identity consistently passing high → validator suggests -0.05 → more creative freedom
    - Smart: doesn't boost PuLID for FACE_ANGLE_EXTREME or SMALL_FACE_REGION
    """
    if base_params is None:
        base_params = get_workflow_params(shot_type)

    base_weight = base_params.get("pulid_weight", 0.9)

    if identity_validator is None:
        return base_weight

    stats = identity_validator.get_rolling_stats(character_id)
    if stats.get("sample_count", 0) == 0:
        return base_weight

    delta = stats.get("suggested_pulid_delta", 0.0)

    # Don't boost PuLID for failures it can't fix
    from identity_types import FailureReason
    common_failure = stats.get("common_failure")
    if common_failure == FailureReason.FACE_ANGLE_EXTREME:
        delta = min(delta, 0.0)
    elif common_failure == FailureReason.SMALL_FACE_REGION:
        delta = 0.0

    adapted = max(0.0, min(1.0, base_weight + delta))
    if abs(delta) > 0.01:
        print(f"      [ADAPTIVE] PuLID weight for {character_id}: {base_weight} → {adapted:.2f} (delta={delta:+.2f})")
    return adapted


def get_shot_workflow_summary(shot: dict) -> str:
    """
    Get a human-readable summary of the workflow selection for logging.
    """
    shot_type = classify_shot_type(shot)
    params = get_workflow_params(shot_type)
    return (
        f"[WORKFLOW] {shot_type}: "
        f"PuLID={params['pulid_weight']}, "
        f"CFG={params['guidance']}, "
        f"steps={params['steps']} "
        f"({params['description']})"
    )


def get_optimal_api(
    shot_type: str,
    character_ids: Optional[List[str]] = None,
    budget_remaining: Optional[float] = None,
    quality_cost_weight: float = 0.8,
) -> List[Dict]:
    """
    Use historical VBench quality data to dynamically rank APIs for a given shot type.

    Scoring formula:
        score = quality_weight * avg_vbench + cost_weight * (1 - normalized_cost)

    If character_ids are present, identity_score is weighted more heavily
    (quality_weight shifts from 0.7 → 0.8, cost_weight from 0.3 → 0.2).

    Args:
        shot_type: One of "portrait", "medium", "wide", "action", "landscape".
        character_ids: Optional list of character IDs in the shot — if present,
            identity preservation is weighted more heavily.
        budget_remaining: Optional remaining budget ($). APIs whose avg_cost
            exceeds this are filtered out.

    Returns:
        Ranked list of dicts:
        [{"api": "KLING_NATIVE", "score": 0.82, "avg_quality": 0.78, "avg_cost": 0.15}, ...]
        Falls back to the static WORKFLOW_TEMPLATES ordering if no historical data exists.
    """
    quality_tracker = QualityTracker()
    api_stats = quality_tracker.get_api_quality_stats()

    # Filter to stats relevant to this shot_type (if the tracker provides per-shot-type breakdowns)
    shot_stats = {}
    for api_name, stats in api_stats.items():
        # Support both flat stats and per-shot-type nested stats
        if isinstance(stats, dict) and shot_type in stats:
            shot_stats[api_name] = stats[shot_type]
        elif isinstance(stats, dict) and "avg_vbench" in stats:
            shot_stats[api_name] = stats

    # Fallback: no historical data → derive ranking from static templates
    if not shot_stats:
        template = WORKFLOW_TEMPLATES.get(shot_type, WORKFLOW_TEMPLATES["medium"])
        primary = template["target_api"]
        fallbacks = template.get("video_fallbacks", [])
        ranked = [{"api": primary, "score": 1.0, "avg_quality": 0.0, "avg_cost": 0.0}]
        for i, fb in enumerate(fallbacks):
            ranked.append({"api": fb, "score": round(0.9 - i * 0.1, 2), "avg_quality": 0.0, "avg_cost": 0.0})
        return ranked

    # --- Determine weights ---
    has_characters = character_ids is not None and len(character_ids) > 0
    quality_weight = quality_cost_weight if has_characters else max(quality_cost_weight - 0.1, 0.5)
    cost_weight = 1.0 - quality_weight

    # Normalize costs across all candidate APIs
    costs = [s.get("avg_cost", 0.0) for s in shot_stats.values()]
    max_cost = max(costs) if costs and max(costs) > 0 else 1.0

    scored: List[Dict] = []
    for api_name, stats in shot_stats.items():
        avg_vbench = stats.get("avg_vbench", 0.0)
        avg_cost = stats.get("avg_cost", 0.0)
        identity_score = stats.get("identity_score", 0.0)

        # Budget filter
        if budget_remaining is not None and avg_cost > budget_remaining:
            continue

        normalized_cost = avg_cost / max_cost

        # Base score
        quality_metric = avg_vbench
        # If characters are present and identity_score is available, blend it in
        if has_characters and identity_score > 0:
            quality_metric = 0.6 * avg_vbench + 0.4 * identity_score

        score = quality_weight * quality_metric + cost_weight * (1 - normalized_cost)

        scored.append({
            "api": api_name,
            "score": round(score, 4),
            "avg_quality": round(avg_vbench, 4),
            "avg_cost": round(avg_cost, 4),
        })

    # Sort descending by score
    scored.sort(key=lambda x: x["score"], reverse=True)

    # If budget filtering removed everything, fall back to static
    if not scored:
        return get_optimal_api(shot_type, character_ids, budget_remaining=None, quality_cost_weight=quality_cost_weight)

    return scored


def get_dynamic_workflow(
    shot_type: str,
    character_ids: Optional[List[str]] = None,
    budget_remaining: Optional[float] = None,
    quality_cost_weight: float = 0.8,
) -> Dict:
    """
    Build a workflow parameter dict that merges static template params
    (PuLID weight, guidance, steps, etc.) with dynamically-selected APIs
    based on historical quality data.

    Args:
        shot_type: One of "portrait", "medium", "wide", "action", "landscape".
        character_ids: Optional list of character IDs — influences API ranking.
        budget_remaining: Optional remaining budget ($) — filters expensive APIs.

    Returns:
        Full workflow params dict with target_api and video_fallbacks updated
        from quality data, all other params from the static template.
    """
    # Start with the static template
    params = get_workflow_params(shot_type)

    # Get quality-ranked APIs
    ranked = get_optimal_api(shot_type, character_ids, budget_remaining, quality_cost_weight)

    if ranked:
        # Best API becomes primary target
        params["target_api"] = ranked[0]["api"]
        # Remaining become fallbacks (preserve order = descending quality score)
        params["video_fallbacks"] = [r["api"] for r in ranked[1:]]
        # Attach ranking metadata for logging / downstream decisions
        params["_api_ranking"] = ranked

    return params
