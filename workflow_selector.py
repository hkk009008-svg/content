"""Classify shots and provide the video router's ordered candidate seed.

Image-provider parameters do not belong here: Gemini owns its remote contract
and the local FLUX.2 workflow is immutable and hash-bound in its deployment
package. The five shot classes remain shared production language for identity
thresholds, motion policy, and video routing.
"""

import re
from datetime import date
from typing import Callable, Dict, List, Mapping, Optional

from domain.provider_catalog import RuntimeSnapshot
from domain.video_engine_policy import (
    VideoCandidateResult,
    build_runtime_snapshot,
    resolve_workflow_candidates,
)

# Shot type -> ordered video-routing seed. Runtime policy is authoritative.
WORKFLOW_TEMPLATES: Dict[str, Dict] = {
    "portrait": {
        # GEMINI_OMNI = Gemini Omni Flash (Preview), Google-first primary since
        # WS2 (Gemini Omni Flash is arena #1). KLING_3_0 = fal Kling v3 Pro
        # (#11 AA i2v arena, 2026-07-11) with `elements` identity binding stays
        # first non-Google fallback. The deprecated native kling-v1-6 adapter
        # is quarantined from automatic routing and remains explicit-only.
        "target_api": "GEMINI_OMNI",
# VEO_NATIVE leads every cascade below and accepts ZERO reference images:
# veo_native.py:381-392 prints the count it was given and passes
# `reference_images=None`, because Vertex forbids image+reference_images
# together. Its own catalog entry says so — scene_decomposer.py:69, "no
# additional references or driving video". Identity therefore comes only from
# the start frame on this route.
#
# NOT reordered here, deliberately. Whether a strong keyframe through Veo beats
# multi-reference binding through Seedance is UNMEASURED, and Veo carries real
# advantages (native audio, quality_score 0.85). Reordering on reasoning alone
# is the mistake this project keeps paying for. Measure first: same shot, same
# character, Veo start-frame versus Seedance reference-to-video, judged by eye.
# Until then, know that a multi-reference set buys nothing on the default route.
        "video_fallbacks": ["VEO_NATIVE", "KLING_3_0", "RUNWAY_GEN4", "SEEDANCE"],
        "description": "Close-up portrait — favor identity-capable video engines and stable facial motion.",
    },
    "medium": {
        # GEMINI_OMNI Google-first primary (WS2); fal Kling v3 Pro (elements
        # identity) first non-Google fallback; native v1.6 is explicit-only.
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "KLING_3_0", "RUNWAY_GEN4", "SEEDANCE", "LTX"],
        "description": "Medium shot — balance identity, dialogue, motion, and scene context.",
    },
    "wide": {
        # GEMINI_OMNI Google-first primary (WS2); old target_api LTX demoted
        # into 2nd fallback slot; old VEO_NATIVE fallback deduped (now the head).
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "LTX", "KLING_3_0", "RUNWAY_GEN4"],
        "description": "Wide establishing shot — favor environment coverage while preserving character continuity.",
    },
    "action": {
        # GEMINI_OMNI Google-first primary (WS2). SEEDANCE (#1 AA i2v arena,
        # 2026-07; multi-reference up to 9 images binds multi-character action)
        # demoted into 2nd fallback slot. Deprecated SORA_NATIVE remains
        # available only when an operator explicitly pins it before sunset;
        # new automatic action routing must not introduce it.
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "SEEDANCE", "KLING_3_0", "RUNWAY_GEN4", "LTX"],
        "description": "Action shot — favor motion-capable engines with identity-aware fallbacks.",
    },
    "landscape": {
        # GEMINI_OMNI Google-first primary (WS2); old target_api LTX demoted;
        # old VEO_NATIVE fallback deduped (now the head).
        "target_api": "GEMINI_OMNI",
        "video_fallbacks": ["VEO_NATIVE", "LTX", "KLING_3_0"],
        "description": "Character-free landscape — favor environment and camera-motion coverage.",
    },
    # Dialogue shots classify as portrait/medium, then the controller picks the
    # first policy-admitted native-audio video route. Any result without
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
                # A landscape-keyword shot that still has a registered character
                # routes to ``wide`` so downstream identity and motion policies
                # do not treat it as character-free.
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
