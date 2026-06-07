"""
Cinema Production Tool — Scene Decomposer
Replaces the monolithic 20-prompt auto-generation (phase_a_generator.py) with
per-scene decomposition. Takes user-defined scenes and converts them into
technically precise image generation prompts via GPT-4o.
"""
from typing import Optional, List

import os
import json
from llm.ensemble import LLMEnsemble
from pipeline_context import PIPELINE_CONTEXT
from domain.project_manager import make_shot
from config.settings import settings
# Camera motion options — canonical list used by per-shot generation.
CAMERA_MOTIONS = [
    "zoom_in_slow", "zoom_out_slow", "zoom_in_fast",
    "pan_right", "pan_left", "pan_up_crane", "pan_down",
    "static_drone", "dolly_in_rapid",
]

# Visual effects — FFMPEG post-production filters available per shot.
VISUAL_EFFECTS = [
    "gritty_contrast", "cinematic_glow", "cyberpunk_glitch",
    "dreamy_blur", "documentary_neutral",
]

# API routing — all available generation engines, augmented with purpose-based
# routing metadata. Existing simple fields (label/category/description) preserved
# for backward compatibility; new fields (modality/best_for/per_shot_cost/
# quality_score/latency_s/status) are additive and optional.
#
# modality:   "video" | "image" | "lipsync" | "tts" | "music" | "foley" | "upscale"
# best_for:   list of purpose tags (see PURPOSE_TAGS below)
# status:     "live" (plumbed + tested) | "beta" (plumbed, untested) | "planned" (not yet wired)
API_REGISTRY = {
    # --- META ---
    "AUTO":          {"label": "Auto (Smart Routing)",  "category": "smart",     "description": "Picks best API per shot type automatically", "modality": "video", "best_for": ["auto"], "status": "live"},

    # --- VIDEO — Native API integrations ---
    "KLING_NATIVE":  {"label": "Kling 3.0 Native",     "category": "native",    "description": "Best faces — subject binding + face_consistency", "modality": "video", "best_for": ["dialogue_close_up", "static_portrait", "style_locked_sequence"], "per_shot_cost": 0.35, "quality_score": 0.86, "latency_s": 90, "status": "live"},
    "SORA_NATIVE":   {"label": "Sora 2 Native",        "category": "native",    "description": "Best motion physics — body momentum, cloth sim", "modality": "video", "best_for": ["action_motion", "macro_detail"], "per_shot_cost": 0.50, "quality_score": 0.88, "latency_s": 120, "status": "live"},
    "VEO_NATIVE":    {"label": "Veo 3.1 Native",       "category": "native",    "description": "Native audio + reference images, 1080p", "modality": "video", "best_for": ["dialogue_close_up", "talking_head_full", "establishing_shot"], "per_shot_cost": 0.40, "quality_score": 0.85, "latency_s": 100, "status": "live", "native_audio": True},
    "RUNWAY_GEN4":   {"label": "Runway Gen-4",         "category": "native",    "description": "Style lock with 3 references, turbo preview", "modality": "video", "best_for": ["style_locked_sequence", "dialogue_close_up"], "per_shot_cost": 0.30, "quality_score": 0.82, "latency_s": 75, "status": "live"},
    "LTX":           {"label": "LTX Video 2.3",        "category": "native",    "description": "4K, keyframe interpolation, cheapest (~$0.06/s)", "modality": "video", "best_for": ["establishing_shot", "macro_detail"], "per_shot_cost": 0.06, "quality_score": 0.74, "latency_s": 60, "status": "live"},

    # --- VIDEO — FAL proxy fallbacks ---
    "KLING_3_0":     {"label": "Kling (FAL Proxy)",    "category": "fal_proxy", "description": "Kling via FAL — reliable fallback", "modality": "video", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.40, "quality_score": 0.84, "latency_s": 110, "status": "live"},
    "SORA_2":        {"label": "Sora 2 (FAL Proxy)",   "category": "fal_proxy", "description": "Sora via FAL — 25s continuous", "modality": "video", "best_for": ["action_motion"], "per_shot_cost": 0.55, "quality_score": 0.87, "latency_s": 130, "status": "live"},
    "VEO":           {"label": "Veo (FAL Proxy)",      "category": "fal_proxy", "description": "Veo via FAL — 4 reference images", "modality": "video", "best_for": ["dialogue_close_up", "establishing_shot"], "per_shot_cost": 0.45, "quality_score": 0.83, "latency_s": 115, "status": "live"},
    "RUNWAY":        {"label": "Runway (FAL Proxy)",   "category": "fal_proxy", "description": "Runway via FAL — legacy fallback", "modality": "video", "best_for": ["style_locked_sequence"], "per_shot_cost": 0.32, "quality_score": 0.80, "latency_s": 80, "status": "live"},

    # --- LIPSYNC / TALKING-HEAD ---
    "MUSETALK":      {"label": "MuseTalk v1.5",        "category": "lipsync",   "description": "Mouth-only overlay on existing video — preserves camera work. Cheap.", "modality": "lipsync", "best_for": ["dialogue_close_up", "talking_head_full"], "per_shot_cost": 0.03, "quality_score": 0.78, "latency_s": 30, "status": "live"},
    "OMNIHUMAN_V1_5":{"label": "Omnihuman v1.5",       "category": "lipsync",   "description": "ByteDance — full talking head from a still image + audio (60s max)", "modality": "lipsync", "best_for": ["talking_head_full"], "per_shot_cost": 0.45, "quality_score": 0.88, "latency_s": 120, "status": "live"},
    "LATENTSYNC":    {"label": "LatentSync v1.6",      "category": "lipsync",   "description": "ByteDance — diffusion-based lipsync, sharper mouth than MuseTalk", "modality": "lipsync", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.05, "quality_score": 0.83, "latency_s": 45, "status": "live"},
    "SYNC_V2":       {"label": "Sync Lipsync v2",      "category": "lipsync",   "description": "Sync Labs older — fallback only, sync.so v3 is preferred", "modality": "lipsync", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.08, "quality_score": 0.79, "latency_s": 40, "status": "live"},
    "SYNC_SO_V3":    {"label": "sync.so v3 (Sync Labs)", "category": "lipsync", "description": "Sync Labs current — best generalist lipsync, handles motion + occlusion", "modality": "lipsync", "best_for": ["dialogue_close_up", "talking_head_full"], "per_shot_cost": 0.12, "quality_score": 0.90, "latency_s": 50, "status": "live"},
    "HEDRA_C3":      {"label": "Hedra Character-3",    "category": "lipsync",   "description": "SOTA portrait talking head — best emotional micro-expressions, full body", "modality": "lipsync", "best_for": ["talking_head_full", "dialogue_close_up"], "per_shot_cost": 0.30, "quality_score": 0.93, "latency_s": 90, "status": "live"},
    "KLING_LIPSYNC_2":{"label": "Kling Lip Sync 2",    "category": "lipsync",   "description": "Kuaishou's Kling-integrated lipsync — pairs natively with Kling video", "modality": "lipsync", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.10, "quality_score": 0.82, "latency_s": 55, "status": "planned"},
    "PIXVERSE_LS2":  {"label": "PixVerse Lip Sync v2", "category": "lipsync",   "description": "PixVerse — quick fallback, average quality", "modality": "lipsync", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.07, "quality_score": 0.75, "latency_s": 35, "status": "planned"},
    "RUNWAY_ACT_ONE":{"label": "Runway Act-One",       "category": "lipsync",   "description": "Driver video transfers BOTH performance and lip sync to character", "modality": "lipsync", "best_for": ["talking_head_full", "dialogue_close_up"], "per_shot_cost": 0.40, "quality_score": 0.91, "latency_s": 100, "status": "live"},

    # --- TTS / DIALOGUE VOICE ---
    "ELEVENLABS_V3": {"label": "ElevenLabs v3",        "category": "tts",       "description": "Current production TTS — multi-voice, 40 delivery styles, voice cloning", "modality": "tts", "best_for": ["dialogue_close_up", "talking_head_full", "narration"], "per_shot_cost": 0.01, "quality_score": 0.92, "latency_s": 3, "status": "live"},
    "ELEVENLABS_DIALOGUE":{"label": "ElevenLabs v3 Dialogue Mode", "category": "tts", "description": "Dedicated dialogue endpoint — natural turn-taking, cross-talk hints, prosody continuity", "modality": "tts", "best_for": ["dialogue_close_up", "talking_head_full"], "per_shot_cost": 0.015, "quality_score": 0.94, "latency_s": 4, "status": "beta"},
    "CARTESIA_SONIC_2":{"label": "Cartesia Sonic 2",   "category": "tts",       "description": "Lowest-latency neural TTS (~75ms), multilingual including Korean, real-time streaming. Requires CARTESIA_API_KEY env.", "modality": "tts", "best_for": ["dialogue_close_up", "narration"], "per_shot_cost": 0.008, "quality_score": 0.88, "latency_s": 1, "status": "live"},
    "OPENAI_AUDIO":  {"label": "OpenAI gpt-4o-audio",  "category": "tts",       "description": "GPT-4o audio mode — expressive, accepts natural-language delivery instructions. Uses your existing OPENAI_API_KEY.", "modality": "tts", "best_for": ["narration", "dialogue_close_up"], "per_shot_cost": 0.012, "quality_score": 0.86, "latency_s": 3, "status": "live"},
    "F5_TTS":        {"label": "F5-TTS (open-weights)", "category": "tts",      "description": "Best open-source TTS — voice cloning from a 5s sample, runs local", "modality": "tts", "best_for": ["dialogue_close_up", "narration"], "per_shot_cost": 0.00, "quality_score": 0.83, "latency_s": 8, "status": "planned"},
    "GPT_SOVITS":    {"label": "GPT-SoVITS v2",        "category": "tts",       "description": "Open-source — strongest few-shot voice cloning, multilingual", "modality": "tts", "best_for": ["dialogue_close_up"], "per_shot_cost": 0.00, "quality_score": 0.81, "latency_s": 12, "status": "planned"},

    # --- IMAGE GEN ALTERNATIVES ---
    "FLUX_DEV":      {"label": "FLUX-Dev (current)",   "category": "image_gen", "description": "Production image gen on RunPod ComfyUI + PuLID", "modality": "image", "best_for": ["any"], "per_shot_cost": 0.03, "quality_score": 0.87, "latency_s": 30, "status": "live"},
    "HIDREAM_I1":    {"label": "HiDream-I1-Full",      "category": "image_gen", "description": "17B params — beats FLUX on photorealism benchmarks. Dispatcher wired in quality_max.py; activates when HiDreamModelLoader detected on pod (requires HiDream ComfyUI node + 35GB model install).", "modality": "image", "best_for": ["static_portrait", "macro_detail", "product_hero"], "per_shot_cost": 0.08, "quality_score": 0.91, "latency_s": 55, "status": "live"},
    "SD3_5_LARGE":   {"label": "Stable Diffusion 3.5 Large", "category": "image_gen", "description": "8B params, strong prompt adherence, alternative refiner", "modality": "image", "best_for": ["establishing_shot", "macro_detail"], "per_shot_cost": 0.05, "quality_score": 0.84, "latency_s": 40, "status": "planned"},

    # --- MUSIC ---
    "SUNO_V5":       {"label": "Suno V5",              "category": "music",     "description": "Generative music with vocals — current SOTA for full songs. Requires SUNO_API_KEY env.", "modality": "music", "best_for": ["music_score"], "per_shot_cost": 0.10, "quality_score": 0.91, "latency_s": 60, "status": "live"},
    "ELEVENLABS_MUSIC":{"label": "ElevenLabs Music",   "category": "music",     "description": "ElevenLabs' new music endpoint — instrumental + vocal, prompt-driven", "modality": "music", "best_for": ["music_score"], "per_shot_cost": 0.12, "quality_score": 0.88, "latency_s": 45, "status": "planned"},
    "STABLE_AUDIO_2":{"label": "Stable Audio 2.0",     "category": "music",     "description": "Stability — 3min stereo, instrumental focus, audio-to-audio remix", "modality": "music", "best_for": ["music_score", "foley"], "per_shot_cost": 0.04, "quality_score": 0.81, "latency_s": 25, "status": "planned"},

    # --- FOLEY / SFX ---
    "STABLE_AUDIO_FOLEY":{"label": "Stable Audio (Foley)", "category": "foley", "description": "Stable Audio 2.0 — long environmental beds (rain, crowd, machinery), up to 190s. Requires STABILITY_API_KEY env.", "modality": "foley", "best_for": ["foley"], "per_shot_cost": 0.03, "quality_score": 0.78, "latency_s": 20, "status": "live"},
    "ADOBE_AUDIO_AI":{"label": "Adobe Audio AI (Project Sonic)", "category": "foley", "description": "Adobe's generative foley — high-quality SFX from text", "modality": "foley", "best_for": ["foley"], "per_shot_cost": 0.05, "quality_score": 0.85, "latency_s": 15, "status": "planned"},

    # --- UPSCALING ---
    "SUPIR_V0Q":     {"label": "SUPIR-v0Q (image)",    "category": "upscale",   "description": "Image upscale — photoreal restoration, best for faces", "modality": "upscale", "best_for": ["upscale_image"], "per_shot_cost": 0.02, "quality_score": 0.92, "latency_s": 35, "status": "live"},
    "TOPAZ_ASTRA":   {"label": "Topaz Video AI Astra", "category": "upscale",   "description": "Video upscale + restoration — 4K/8K, the production benchmark", "modality": "upscale", "best_for": ["upscale_video"], "per_shot_cost": 0.15, "quality_score": 0.94, "latency_s": 240, "status": "planned"},
    "SEEDVR2":       {"label": "SeedVR2",              "category": "upscale",   "description": "Cloud video upscale, currently wired in post-process", "modality": "upscale", "best_for": ["upscale_video"], "per_shot_cost": 0.08, "quality_score": 0.86, "latency_s": 90, "status": "live"},
    "CCSR":          {"label": "CCSR (image)",         "category": "upscale",   "description": "Real-world photo restoration — environments, lighter than SUPIR", "modality": "upscale", "best_for": ["upscale_image"], "per_shot_cost": 0.015, "quality_score": 0.88, "latency_s": 25, "status": "planned"},
}
TARGET_APIS = list(API_REGISTRY.keys())

# Purpose tags — the abstraction over shot-type that drives purpose-based routing.
# Each purpose maps to a ranked list of API keys, best-first. The orchestrator
# walks this list, skipping APIs that are disabled or beyond budget, and the
# first survivor wins.
PURPOSE_TAGS = [
    "dialogue_close_up",       # face-critical talking
    "talking_head_full",       # direct-to-camera dialogue, full body
    "action_motion",           # body movement, physics
    "static_portrait",         # non-talking portrait
    "establishing_shot",       # wide environment, no characters or distant ones
    "macro_detail",            # close-up texture / object
    "style_locked_sequence",   # repeated atmosphere across shots
    "narration",               # voiceover, no on-screen speaker
    "music_score",             # background music generation
    "foley",                   # SFX / environmental sound
    "upscale_image",           # still image super-resolution
    "upscale_video",           # video super-resolution
    # Product / commercial work
    "product_hero",            # beauty pass on a product (no characters; product is the subject)
    "product_in_scene",        # product placed within a character scene (e.g., character drinking the beverage)
    "product_reveal_motion",   # animated reveal/unveil of a product (rotating, lighting transition)
]

# Per-purpose ranked picks. The first entry is the recommended choice; the rest
# are ordered fallbacks. The orchestrator uses these when target_api='AUTO' or
# when a per-purpose route is explicitly requested. Edit here, not in code.
PURPOSE_API_RANKING = {
    "dialogue_close_up":    ["HEDRA_C3", "KLING_NATIVE", "VEO_NATIVE", "SYNC_SO_V3", "LATENTSYNC", "MUSETALK"],
    "talking_head_full":    ["HEDRA_C3", "RUNWAY_ACT_ONE", "OMNIHUMAN_V1_5", "VEO_NATIVE", "SYNC_SO_V3"],
    "action_motion":        ["SORA_NATIVE", "SORA_2", "KLING_NATIVE", "RUNWAY_GEN4"],
    "static_portrait":      ["KLING_NATIVE", "RUNWAY_GEN4", "FLUX_DEV", "HIDREAM_I1"],
    "establishing_shot":    ["LTX", "VEO_NATIVE"],
    "macro_detail":         ["SORA_NATIVE", "LTX", "FLUX_DEV", "HIDREAM_I1"],
    "style_locked_sequence":["RUNWAY_GEN4", "KLING_NATIVE", "VEO_NATIVE"],
    "narration":            ["ELEVENLABS_V3", "CARTESIA_SONIC_2", "OPENAI_AUDIO", "F5_TTS"],
    "music_score":          ["SUNO_V5", "ELEVENLABS_MUSIC", "STABLE_AUDIO_2"],
    "foley":                ["STABLE_AUDIO_FOLEY", "ADOBE_AUDIO_AI"],
    "upscale_image":        ["SUPIR_V0Q", "CCSR"],
    "upscale_video":        ["TOPAZ_ASTRA", "SEEDVR2"],
    # Product / commercial routing:
    # - product_hero needs FLUX-class image quality + Mochi 2 / Sora 2 for the
    #   beauty-pass motion (their physics handles reflections + rotation best).
    # - product_in_scene blends with character-shot routing; pick engines that
    #   handle BOTH face and product (Kling Native is strongest here).
    # - product_reveal_motion is the most demanding — needs Sora's physics for
    #   light glints + smooth rotation. Mochi 2 is a close second.
    "product_hero":             ["HIDREAM_I1", "FLUX_DEV", "SORA_NATIVE", "SD3_5_LARGE", "LTX"],
    "product_in_scene":         ["KLING_NATIVE", "VEO_NATIVE", "RUNWAY_GEN4", "SORA_NATIVE"],
    "product_reveal_motion":    ["SORA_NATIVE", "KLING_NATIVE", "RUNWAY_GEN4"],
}


# Provider → API key prefix mapping for billing attribution. The user signs up
# with each provider separately and gets billed by them (FAL prepaid credits,
# ElevenLabs subscription, etc.). This table is the source of truth for which
# provider owns which API.
BILLING_PROVIDERS = {
    "FAL_AI": [
        "KLING_3_0", "SORA_2", "VEO", "RUNWAY",
        "MUSETALK", "OMNIHUMAN_V1_5", "LATENTSYNC", "SYNC_V2",
        "SYNC_SO_V3", "HEDRA_C3", "KLING_LIPSYNC_2", "PIXVERSE_LS2", "RUNWAY_ACT_ONE",
        "SEEDVR2",
    ],
    "KLING_DIRECT":     ["KLING_NATIVE"],
    "OPENAI":           ["SORA_NATIVE", "OPENAI_AUDIO"],
    "GOOGLE_VERTEX":    ["VEO_NATIVE"],
    "RUNWAY_DIRECT":    ["RUNWAY_GEN4"],
    "LTX_DIRECT":       ["LTX"],
    "ELEVENLABS":       ["ELEVENLABS_V3", "ELEVENLABS_DIALOGUE", "ELEVENLABS_MUSIC"],
    "CARTESIA":         ["CARTESIA_SONIC_2"],
    "OPEN_WEIGHTS":     ["F5_TTS", "GPT_SOVITS"],  # zero marginal cost — local GPU only
    "RUNPOD_GPU":       ["FLUX_DEV", "HIDREAM_I1", "SD3_5_LARGE", "SUPIR_V0Q", "CCSR"],
    "SUNO":             ["SUNO_V5"],
    "STABILITY":        ["STABLE_AUDIO_2", "STABLE_AUDIO_FOLEY"],
    "ADOBE":            ["ADOBE_AUDIO_AI"],
    "TOPAZ":            ["TOPAZ_ASTRA"],
}


def estimate_short_cost(
    shot_count: int = 60,
    has_dialogue: bool = True,
    dialogue_shot_ratio: float = 0.5,
    quality_tier: str = "production",
    candidate_count: int = 1,   # >1 only for max tier
) -> dict:
    """Rough cost estimate for a 60-shot short. Returns per-category breakdown.

    Args:
        shot_count: Total shots in the short.
        has_dialogue: Whether any shots have spoken dialogue.
        dialogue_shot_ratio: Fraction of shots that are dialogue shots.
        quality_tier: 'production' (single attempt) | 'max' (N candidates × all post-passes).
        candidate_count: For max tier, N from best-of-N. Multiplies image gen cost.

    Returns:
        {
          "totals": {"image_gen": $, "video_gen": $, "lipsync": $, "tts": $,
                     "music": $, "foley": $, "upscale": $, "llm": $, "grand_total": $},
          "by_provider": {"FAL_AI": $, "ElevenLabs": $, ...},
          "per_shot": {"avg": $, "worst": $},
          "notes": [warnings about beta/planned APIs etc.]
        }
    """
    dialogue_shots = int(shot_count * dialogue_shot_ratio) if has_dialogue else 0
    notes = []

    is_max = quality_tier == "max"

    # ----- Image gen (always, one per shot, multiplied by candidate count for max) -----
    img_cost_per = API_REGISTRY["FLUX_DEV"]["per_shot_cost"]
    if is_max:
        img_cost_per += API_REGISTRY["SUPIR_V0Q"]["per_shot_cost"]  # SUPIR post-pass
    image_total = img_cost_per * shot_count * candidate_count

    # ----- Video gen (one per shot, no candidate multiplier — only one video per shot) -----
    # Average video cost across the smart-routing mix (LTX cheap, Sora expensive)
    video_avg = 0.30  # weighted across LTX/Kling/Sora/Veo mix
    video_total = video_avg * shot_count

    # ----- Lipsync (only dialogue shots) -----
    if dialogue_shots > 0:
        lipsync_per = API_REGISTRY["HEDRA_C3"]["per_shot_cost"]  # default routed pick
    else:
        lipsync_per = 0.0
    lipsync_total = lipsync_per * dialogue_shots

    # ----- TTS (per dialogue line; assume avg 4 lines per dialogue shot) -----
    tts_lines = dialogue_shots * 4 if has_dialogue else 0
    tts_per_line = API_REGISTRY["ELEVENLABS_V3"]["per_shot_cost"]
    tts_total = tts_per_line * tts_lines

    # ----- Music (1 track per short) -----
    music_total = API_REGISTRY["SUNO_V5"]["per_shot_cost"] if has_dialogue else 0.10

    # ----- Foley (varies — assume 1 per 3 shots) -----
    foley_total = API_REGISTRY["STABLE_AUDIO_FOLEY"]["per_shot_cost"] * (shot_count // 3)

    # ----- Video upscale (final master pass) -----
    upscale_total = API_REGISTRY["SEEDVR2"]["per_shot_cost"] if is_max else 0.0

    # ----- LLM (script + decompose + per-shot prompt optimizer) -----
    # Claude/GPT-4o pricing is per token. Rough estimate: ~$0.50 per short for
    # script generation + scene decomposition + per-shot prompt optimization.
    llm_total = 0.50 + (0.01 * shot_count)  # 1 cent per shot for prompt optimization

    totals = {
        "image_gen": round(image_total, 2),
        "video_gen": round(video_total, 2),
        "lipsync": round(lipsync_total, 2),
        "tts": round(tts_total, 2),
        "music": round(music_total, 2),
        "foley": round(foley_total, 2),
        "upscale": round(upscale_total, 2),
        "llm": round(llm_total, 2),
    }
    totals["grand_total"] = round(sum(totals.values()), 2)

    by_provider = {
        "FAL_AI": round(video_total + lipsync_total + upscale_total, 2),
        "ElevenLabs": round(tts_total, 2),
        "Suno": round(music_total, 2) if has_dialogue else 0,
        "Stability": round(foley_total, 2),
        "Anthropic/OpenAI (LLM)": round(llm_total, 2),
        "RunPod (FLUX GPU)": round(image_total, 2),
    }

    per_shot = {
        "avg": round(totals["grand_total"] / max(shot_count, 1), 3),
        "image_only": round(img_cost_per * candidate_count, 3),
        "with_dialogue": round(img_cost_per * candidate_count + lipsync_per + tts_per_line * 4, 3),
    }

    if is_max and candidate_count > 1:
        notes.append(f"Max tier with N={candidate_count} multiplies image gen cost {candidate_count}x")
    if not has_dialogue:
        notes.append("Dialogue costs excluded (no dialogue in this short)")

    return {
        "totals": totals,
        "by_provider": by_provider,
        "per_shot": per_shot,
        "shot_count": shot_count,
        "dialogue_shots": dialogue_shots,
        "quality_tier": quality_tier,
        "notes": notes,
    }


def rank_apis_for_purpose(purpose: str, *, status_filter=("live", "beta"),
                          max_per_shot_cost=None, exclude=()):
    """Return APIs ordered best-first for a given purpose.

    Filters to entries whose status is in status_filter and (if given) whose
    per_shot_cost is below max_per_shot_cost. Used by the orchestrator to pick
    the best API for a shot. UI uses it to render the per-purpose picker.

    Returns: list of (api_key, api_dict) tuples.
    """
    rank = PURPOSE_API_RANKING.get(purpose, [])
    out = []
    for key in rank:
        if key in exclude:
            continue
        info = API_REGISTRY.get(key)
        if not info:
            continue
        if status_filter and info.get("status", "live") not in status_filter:
            continue
        cost = info.get("per_shot_cost", 0.0)
        if max_per_shot_cost is not None and cost > max_per_shot_cost:
            continue
        out.append((key, info))
    return out

# Music moods
MUSIC_MOODS = [
    # Tension / Dark
    "suspense", "thriller", "horror", "noir", "dystopian",
    # Emotional / Dramatic
    "melancholic", "romantic", "bittersweet", "grief", "hopeful",
    # Energy / Action
    "epic", "action", "triumphant", "chase",
    # Ambient / Atmosphere
    "ethereal", "dreamy", "meditative", "cosmic",
    # Modern / Urban
    "cyberpunk", "corporate", "gritty", "urban", "uplifting",
    # Period / Genre
    "jazz_noir", "classical", "western", "electronic_minimal",
]


def _build_cinedecompose_system_prompt(
    target_shots: int,
    char_descriptions: list,
    loc_description: str,
    loc_lighting: str,
    loc_time: str,
    loc_weather: str,
    style_ctx: str,
    research_ctx: str,
    global_settings: dict,
) -> str:
    """Build the CineDecompose v1.0 system prompt.

    Bundle-B 2.3 (2026-05-24): extracted to a single source of truth.
    Previously this 75-line f-string template was duplicated verbatim in
    `decompose_scene` and `competitive_decompose_scene` (~150 LOC of
    drift hazard). HC1-HC5, the schema, the example, and the tripwires
    are now defined here once — both callers render with the same prompt.

    The template is a single triple-quoted f-string so editing any one
    constraint or rule lands consistently across both call paths. To add
    a new variable, extend this signature; both call sites already pass
    the same locals.
    """
    return f"""<SYSTEM_PERSONA>
You are "CineDecompose v1.0". You operate as a strict cinematic shot decomposition engine.
Your singular purpose is to decompose scenes into exactly {target_shots} technically precise shot descriptions.
You follow the OUTPUT_SCHEMA with zero deviation. You do not improvise, embellish, or add unrequested content.
TONE: Strictly technical. Zero creative flourish. Output structured data only.
</SYSTEM_PERSONA>

<HARD_CONSTRAINTS>
HC1-IDENTITY_FIREWALL: You MUST NEVER describe any character's face, hair color, hair style,
    glasses, skin tone, eye color, facial structure, age appearance, or body shape.
    The face-locking system handles identity from a reference photo.
    If you describe the face, it CONFLICTS with the face-lock and produces a DIFFERENT PERSON.
    VIOLATION OF HC1 = PIPELINE FAILURE.

HC2-SCHEMA_LOCK: Every shot prompt MUST contain exactly these 5 labeled sections in order:
    [SHOT] [SCENE] [ACTION] [OUTFIT] [QUALITY]. No other sections. No unlabeled text.

HC3-LOCATION_LOCK: The [SCENE] section MUST describe the SAME location across all shots.
    Use identical environment details. Only camera angle and framing change between shots.

HC4-LIGHTING_LOCK: Light direction, color temperature, and intensity MUST be identical
    across all shots in this scene. Specify once, repeat verbatim.

HC5-FACE_DIRECTION: Every [ACTION] MUST include the character facing the camera.
    Use: "facing the camera", "looking toward the camera", "three-quarter view toward camera".
    NEVER: "turning away", "looking down", "silhouette", "back to camera".
</HARD_CONSTRAINTS>

<TRIPWIRES>
Before outputting, verify:
[T1] Does ANY prompt contain words describing face/hair/skin/glasses/eyes? → REMOVE THEM.
[T2] Does every prompt contain all 5 sections [SHOT][SCENE][ACTION][OUTFIT][QUALITY]? → If not, ADD missing sections.
[T3] Is the location description identical across all shots? → If not, UNIFY.
[T4] Is the lighting description identical across all shots? → If not, UNIFY.
</TRIPWIRES>

<OUTPUT_SCHEMA>
Each shot prompt follows this exact structure:

"[SHOT] {{shot type}}, {{focal length}} lens, {{depth of field}}, {{camera height and angle}}.
[SCENE] {{environment description}}, {{weather}}, {{lighting: direction, color temp, fill ratio}}, {{atmospheric depth cue: haze, dust, volumetric light}}.
[ACTION] The character {{physical action}}, {{camera-facing direction}}, {{interaction with props/environment}}, {{weight and physicality of movement}}.
[OUTFIT] {{clothing items, fabric texture, fit — NO hair, face, or body description}}.
[QUALITY] Photorealistic, visible skin pores and subsurface scattering, shallow depth of field with circular bokeh, natural film grain ISO 400, volumetric atmospheric lighting, micro-detail in fabric weave and material texture, no AI artifacts, no smooth plastic skin, no over-saturated colors."
</OUTPUT_SCHEMA>

<EXAMPLE>
"[SHOT] Medium shot, 85mm f/1.4 lens, shallow depth of field, camera at eye level slightly below subject. [SCENE] A snow-covered park with bare oak trees lining a path, overcast sky, soft diffused natural light at 4500K, fill ratio 1:3 from camera-left, faint breath vapor in cold air. [ACTION] The character walks toward the camera along the snow-covered path with natural gait weight, golden retriever on a leash in right hand, looking directly at the camera with a gentle expression. [OUTFIT] Red wool peacoat with visible fabric texture over cream turtleneck knit, dark fitted jeans, black leather ankle boots with slight wear. [QUALITY] Photorealistic, visible skin pores and subsurface scattering, shallow depth of field with circular bokeh, natural film grain ISO 400, volumetric cold-air haze, micro-detail in wool weave, no AI artifacts, no smooth plastic skin."
</EXAMPLE>

<SCENE_DATA>
[CHARACTERS IN THIS SCENE]:
{chr(10).join(char_descriptions)}
(NOTE: Character names are for reference ONLY. Do NOT describe their physical appearance.)

[LOCATION]:
{loc_description}
Lighting: {loc_lighting}
Time of day: {loc_time}
Weather: {loc_weather}

{style_ctx}
{research_ctx}
</SCENE_DATA>

<ADDITIONAL_RULES>
R1. Shots follow physical logic — characters do not teleport between shots.
R2. Camera angles are physically achievable and cinematic.
R3. Every shot specifies environmental Foley sound effects in scene_foley field.
R4. Aspect ratio: {global_settings.get('aspect_ratio', '16:9')} widescreen.
R5. Set target_api intelligently using the API EXPERTISE below. Do NOT default to "AUTO" — pick the best API for each shot.
R6. In [OUTFIT], describe ONLY clothing and accessories — NEVER hair, face, body, or physical traits.
</ADDITIONAL_RULES>

{PIPELINE_CONTEXT}

Output ONLY a valid JSON array of shot objects. No markdown wrapping. No explanation."""


def decompose_scene(
    scene: dict,
    characters: List[dict],
    location: dict,
    global_settings: dict,
    style_rules: Optional[dict] = None,
) -> List[dict]:
    """
    Takes a user-defined scene and produces 2-5 shot breakdowns via GPT-4o.
    Each shot includes: image prompt, camera motion, visual effect, target API,
    foley description, and character/position metadata.

    Args:
        scene: The Scene dict from the project
        characters: List of CharacterRecord dicts for characters in this scene
        location: The LocationRecord dict for this scene's location
        global_settings: Project global settings (aspect ratio, color palette, etc.)
        style_rules: Optional cinematography/color rules from style_director

    Returns:
        List of shot dicts ready for continuity enhancement and image generation.
    """
    import openai

    api_key = settings.openai_api_key
    if not api_key:
        print("❌ OPENAI_API_KEY not set. Cannot decompose scene.")
        return _fallback_decompose(scene, characters, location)

    client = openai.OpenAI(api_key=api_key, timeout=120.0)

    # Build character descriptions for the prompt
    char_descriptions = []
    char_id_map = {}
    for c in characters:
        char_descriptions.append(
            f"- {c['name']} (ID: {c['id']}): {c.get('physical_traits', c.get('description', ''))}"
        )
        char_id_map[c["name"].lower()] = c["id"]

    # Build location context
    loc_description = location.get("description", "an unspecified location")
    loc_lighting = location.get("lighting", "natural lighting")
    loc_time = location.get("time_of_day", "day")
    loc_weather = location.get("weather", "clear")

    # Style rules context
    style_ctx = ""
    if style_rules:
        style_ctx = f"""
[STYLE CONSTRAINTS]:
- Cinematography: {style_rules.get('cinematography_rules', 'cinematic, photorealistic')}
- Color Grading: {style_rules.get('color_grading_palette', global_settings.get('color_palette', 'natural cinematic'))}
- Mood: {style_rules.get('director_vision', scene.get('mood', 'neutral'))}
"""

    # Research-enhanced context — Tavily searches for real cinematography techniques
    research_ctx = ""
    try:
        from research_engine import research_cinematography
        mood = scene.get("mood", "cinematic")
        action = scene.get("action", "")
        reference = research_cinematography(mood, loc_description, action)
        if reference:
            research_ctx = f"\n{reference}\n"
    except (ImportError, RuntimeError) as e:
        pass  # Research is optional — never blocks generation

    # Target shot count based on duration
    duration = scene.get("duration_seconds", 5)
    target_shots = max(2, min(5, int(duration / 2.5)))

    system_prompt = _build_cinedecompose_system_prompt(
        target_shots=target_shots,
        char_descriptions=char_descriptions,
        loc_description=loc_description,
        loc_lighting=loc_lighting,
        loc_time=loc_time,
        loc_weather=loc_weather,
        style_ctx=style_ctx,
        research_ctx=research_ctx,
        global_settings=global_settings,
    )

    shot_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed photorealistic image generation prompt with location, action, wardrobe, and quality cues while leaving facial identity to reference locking"},
                "camera": {"type": "string", "enum": CAMERA_MOTIONS},
                "visual_effect": {"type": "string", "enum": VISUAL_EFFECTS},
                "target_api": {"type": "string", "enum": TARGET_APIS},
                "scene_foley": {"type": "string", "description": "Environmental sound effects for this moment"},
                "characters_in_frame": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Character IDs visible in this shot",
                },
                "action_context": {"type": "string", "description": "What is physically happening in this shot for temporal continuity"},
            },
            "required": ["prompt", "camera", "visual_effect", "target_api", "scene_foley", "characters_in_frame", "action_context"],
        },
    }

    user_prompt = f"""Decompose this scene into exactly {target_shots} shots:

SCENE TITLE: {scene.get('title', 'Untitled')}
ACTION: {scene.get('action', '')}
DIALOGUE: {scene.get('dialogue', 'None')}
MOOD: {scene.get('mood', 'neutral')}
CAMERA DIRECTION: {scene.get('camera_direction', 'Cinematic, varied angles')}
DURATION: ~{duration} seconds

Character IDs to use in characters_in_frame: {json.dumps([c['id'] for c in characters])}

Output ONLY the raw JSON array. No markdown wrapping."""

    full_system = system_prompt + "\n\nJSON Schema:\n" + json.dumps(shot_schema, indent=2)

    try:
        from web_research import run_with_tools

        # Enhance system prompt to encourage tool use
        full_system_with_tools = full_system + """

IMPORTANT: You have access to web search (tavily_search) and URL scraping (firecrawl_scrape_url) tools.
Use them when you need to research:
- Specific cinematography techniques for a scene type
- Visual reference for a location or setting
- How real films shoot similar scenes
Only use tools if they would genuinely improve shot quality. Skip if the scene is straightforward."""

        raw = run_with_tools(
            client, "gpt-4o",
            system_prompt=full_system_with_tools,
            user_prompt=user_prompt,
            max_tool_rounds=2,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)

        # Handle both {"shots": [...]} and bare [...] formats
        shots = parsed if isinstance(parsed, list) else parsed.get("shots", [])

        # Debug: if no shots found, check what keys we got
        if not shots and isinstance(parsed, dict):
            # Case 1: GPT-4o returned a single shot object (has 'prompt' key) → wrap in list
            if "prompt" in parsed:
                shots = [parsed]
                print(f"   [DEBUG] GPT-4o returned single shot object — wrapped in list")
            else:
                # Case 2: Shots nested under a non-standard key → find array of dicts
                for key in parsed:
                    val = parsed[key]
                    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                        shots = val
                        print(f"   [DEBUG] Found shots under key '{key}': {len(shots)} items")
                        break

        # Validate and enrich shots
        validated = []
        for i, shot in enumerate(shots):
            char_ids = shot.get("characters_in_frame", [c["id"] for c in characters])
            shot_record = make_shot(
                prompt=shot.get("prompt", ""),
                camera=shot.get("camera", "zoom_in_slow") if shot.get("camera") in CAMERA_MOTIONS else "zoom_in_slow",
                visual_effect=shot.get("visual_effect", "cinematic_glow") if shot.get("visual_effect") in VISUAL_EFFECTS else "cinematic_glow",
                target_api=shot.get("target_api", "AUTO") if shot.get("target_api") in TARGET_APIS else "AUTO",
                scene_foley=shot.get("scene_foley", "ambient room tone"),
                characters_in_frame=char_ids,
                primary_character=char_ids[0] if char_ids else "",
                shot_id=f"shot_{scene.get('id', 'scene')}_{i}",
            )
            shot_record["action_context"] = shot.get("action_context", scene.get("action", ""))
            shot_record["intent_notes"] = scene.get("action", "")
            validated.append(shot_record)

        print(f"   ✅ Decomposed scene '{scene.get('title')}' into {len(validated)} shots")
        return validated

    except Exception as e:
        import traceback
        print(f"   [ERROR] GPT-4o decomposition failed: {e}")
        traceback.print_exc()
        return _fallback_decompose(scene, characters, location)


def competitive_decompose_scene(
    scene: dict,
    characters: List[dict],
    location: dict,
    global_settings: dict,
    style_rules: Optional[dict] = None,
) -> List[dict]:
    """
    Multi-LLM competitive scene decomposition.

    Generates shot breakdowns from GPT-4o and Claude Sonnet in parallel via
    LLMEnsemble, has the Chief Director (judge model) pick the better one,
    and returns the winning shot list.  Falls back to the single-model
    ``decompose_scene()`` if the ensemble pipeline fails.

    Args:
        scene: The Scene dict from the project
        characters: List of CharacterRecord dicts for characters in this scene
        location: The LocationRecord dict for this scene's location
        global_settings: Project global settings (aspect ratio, color palette, etc.)
        style_rules: Optional cinematography/color rules from style_director

    Returns:
        List of shot dicts ready for continuity enhancement and image generation.
    """

    # ------------------------------------------------------------------
    # 1. Build character descriptions (identical to decompose_scene)
    # ------------------------------------------------------------------
    char_descriptions = []
    char_id_map = {}
    for c in characters:
        char_descriptions.append(
            f"- {c['name']} (ID: {c['id']}): {c.get('physical_traits', c.get('description', ''))}"
        )
        char_id_map[c["name"].lower()] = c["id"]

    # ------------------------------------------------------------------
    # 2. Build location context
    # ------------------------------------------------------------------
    loc_description = location.get("description", "an unspecified location")
    loc_lighting = location.get("lighting", "natural lighting")
    loc_time = location.get("time_of_day", "day")
    loc_weather = location.get("weather", "clear")

    # ------------------------------------------------------------------
    # 3. Style rules context
    # ------------------------------------------------------------------
    style_ctx = ""
    if style_rules:
        style_ctx = f"""
[STYLE CONSTRAINTS]:
- Cinematography: {style_rules.get('cinematography_rules', 'cinematic, photorealistic')}
- Color Grading: {style_rules.get('color_grading_palette', global_settings.get('color_palette', 'natural cinematic'))}
- Mood: {style_rules.get('director_vision', scene.get('mood', 'neutral'))}
"""

    # ------------------------------------------------------------------
    # 4. Research-enhanced context (optional)
    # ------------------------------------------------------------------
    research_ctx = ""
    try:
        from research_engine import research_cinematography
        mood = scene.get("mood", "cinematic")
        action = scene.get("action", "")
        reference = research_cinematography(mood, loc_description, action)
        if reference:
            research_ctx = f"\n{reference}\n"
    except (ImportError, RuntimeError) as e:
        pass  # Research is optional — never blocks generation

    # ------------------------------------------------------------------
    # 5. Target shot count based on duration
    # ------------------------------------------------------------------
    duration = scene.get("duration_seconds", 5)
    target_shots = max(2, min(5, int(duration / 2.5)))

    # ------------------------------------------------------------------
    # 6. Build system prompt (shared with decompose_scene)
    # ------------------------------------------------------------------
    system_prompt = _build_cinedecompose_system_prompt(
        target_shots=target_shots,
        char_descriptions=char_descriptions,
        loc_description=loc_description,
        loc_lighting=loc_lighting,
        loc_time=loc_time,
        loc_weather=loc_weather,
        style_ctx=style_ctx,
        research_ctx=research_ctx,
        global_settings=global_settings,
    )

    shot_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed photorealistic image generation prompt including ALL character physical descriptions and FULL location description"},
                "camera": {"type": "string", "enum": CAMERA_MOTIONS},
                "visual_effect": {"type": "string", "enum": VISUAL_EFFECTS},
                "target_api": {"type": "string", "enum": TARGET_APIS},
                "scene_foley": {"type": "string", "description": "Environmental sound effects for this moment"},
                "characters_in_frame": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Character IDs visible in this shot",
                },
                "action_context": {"type": "string", "description": "What is physically happening in this shot for temporal continuity"},
            },
            "required": ["prompt", "camera", "visual_effect", "target_api", "scene_foley", "characters_in_frame", "action_context"],
        },
    }

    user_prompt = f"""Decompose this scene into exactly {target_shots} shots:

SCENE TITLE: {scene.get('title', 'Untitled')}
ACTION: {scene.get('action', '')}
DIALOGUE: {scene.get('dialogue', 'None')}
MOOD: {scene.get('mood', 'neutral')}
CAMERA DIRECTION: {scene.get('camera_direction', 'Cinematic, varied angles')}
DURATION: ~{duration} seconds

Character IDs to use in characters_in_frame: {json.dumps([c['id'] for c in characters])}

Output ONLY the raw JSON array. No markdown wrapping."""

    full_system = system_prompt + "\n\nJSON Schema:\n" + json.dumps(shot_schema, indent=2)

    # ------------------------------------------------------------------
    # 7. Run competitive generation via LLMEnsemble
    # ------------------------------------------------------------------
    try:
        ensemble = LLMEnsemble()
        result = ensemble.competitive_generate(
            task_type="decompose",
            system_prompt=full_system,
            user_prompt=user_prompt,
            json_mode=True,
        )

        print(
            f"   [Ensemble] Models used: {result.models_used} | "
            f"Scores: {result.scores} | Winner: {result.models_used[result.winner_index]}"
        )
        print(f"   [Ensemble] Judge reasoning: {result.reasoning[:200]}")

        winning_raw = result.winner_content
        if winning_raw is None:
            print("   [Ensemble] Winning candidate was None — falling back to decompose_scene()")
            return decompose_scene(scene, characters, location, global_settings, style_rules)

        # ------------------------------------------------------------------
        # 8. Parse the winning output into a shot list
        # ------------------------------------------------------------------
        if isinstance(winning_raw, str):
            # Strip possible markdown fences
            cleaned = winning_raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned.strip())
        elif isinstance(winning_raw, (dict, list)):
            parsed = winning_raw
        else:
            parsed = json.loads(str(winning_raw))

        # Handle both {"shots": [...]} and bare [...] formats
        shots = parsed if isinstance(parsed, list) else parsed.get("shots", [])

        if not shots and isinstance(parsed, dict):
            if "prompt" in parsed:
                shots = [parsed]
            else:
                for key in parsed:
                    val = parsed[key]
                    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                        shots = val
                        break

        if not shots:
            print("   [Ensemble] Could not extract shots from winner — falling back to decompose_scene()")
            return decompose_scene(scene, characters, location, global_settings, style_rules)

        # ------------------------------------------------------------------
        # 9. Validate and enrich each shot (camera, visual_effect, target_api)
        # ------------------------------------------------------------------
        validated = []
        for i, shot in enumerate(shots):
            char_ids = shot.get("characters_in_frame", [c["id"] for c in characters])
            shot_record = make_shot(
                prompt=shot.get("prompt", ""),
                camera=shot.get("camera", "zoom_in_slow") if shot.get("camera") in CAMERA_MOTIONS else "zoom_in_slow",
                visual_effect=shot.get("visual_effect", "cinematic_glow") if shot.get("visual_effect") in VISUAL_EFFECTS else "cinematic_glow",
                target_api=shot.get("target_api", "AUTO") if shot.get("target_api") in TARGET_APIS else "AUTO",
                scene_foley=shot.get("scene_foley", "ambient room tone"),
                characters_in_frame=char_ids,
                primary_character=char_ids[0] if char_ids else "",
                shot_id=f"shot_{scene.get('id', 'scene')}_{i}",
            )
            shot_record["action_context"] = shot.get("action_context", scene.get("action", ""))
            shot_record["intent_notes"] = scene.get("action", "")
            shot_record["ensemble_winner"] = result.models_used[result.winner_index]
            shot_record["ensemble_scores"] = result.scores
            validated.append(shot_record)

        print(
            f"   ✅ [Competitive] Decomposed scene '{scene.get('title')}' into "
            f"{len(validated)} shots (winner: {result.models_used[result.winner_index]})"
        )
        return validated

    except Exception as e:
        import traceback
        print(f"   [Ensemble] Competitive decomposition failed: {e}")
        traceback.print_exc()
        print("   [Ensemble] Falling back to single-model decompose_scene()")
        return decompose_scene(scene, characters, location, global_settings, style_rules)


def _fallback_decompose(
    scene: dict,
    characters: List[dict],
    location: dict,
) -> List[dict]:
    """Simple fallback decomposition when GPT-4o is unavailable."""
    char_ids = [c["id"] for c in characters]
    loc_desc = location.get("description", "a cinematic location")
    action = scene.get("action", "standing in the scene")
    scene_id = scene.get("id", "scene")
    subject_phrase = "the character" if len(char_ids) == 1 else "the characters"

    shots = [
        make_shot(
            prompt=f"[SHOT] Establishing wide shot, 24mm lens, deep depth of field, camera at low angle. [SCENE] {loc_desc}, natural ambient lighting. [ACTION] {subject_phrase} perform the scene action, facing the camera, with grounded physical weight and clear interaction with the environment. [OUTFIT] Current wardrobe with visible fabric texture and material detail. [QUALITY] Photorealistic, visible skin pores and subsurface scattering, natural film grain ISO 400, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin.",
            camera="zoom_in_slow",
            visual_effect="cinematic_glow",
            target_api="AUTO",
            scene_foley="ambient environmental sound",
            characters_in_frame=char_ids,
            primary_character=char_ids[0] if char_ids else "",
            shot_id=f"shot_{scene_id}_0",
        ),
        make_shot(
            prompt=f"[SHOT] Medium close-up, 85mm f/1.4 lens, shallow depth of field, eye-level camera. [SCENE] {loc_desc}, natural motivated key light from camera-left. [ACTION] The primary character continues the scene action, looking directly at the camera with physically motivated movement and prop interaction. [OUTFIT] Current wardrobe with visible fabric texture and natural folds. [QUALITY] Photorealistic, visible skin pores and subsurface scattering, shallow depth of field with circular bokeh, natural film grain ISO 400, no AI artifacts, no smooth plastic skin.",
            camera="dolly_in_rapid",
            visual_effect="cinematic_glow",
            target_api="AUTO",
            scene_foley="subtle environmental ambience",
            characters_in_frame=char_ids[:1],
            primary_character=char_ids[0] if char_ids else "",
            shot_id=f"shot_{scene_id}_1",
        ),
    ]

    for shot in shots:
        shot["action_context"] = action
        shot["intent_notes"] = action

    print(f"   ⚠️ Used fallback decomposition for scene '{scene.get('title')}' → {len(shots)} shots")
    return shots


def update_scene_shots(
    project: dict,
    scene_id: str,
    shots: list[dict],
    timeout: float = 10,
) -> None:
    """Save decomposed shots back into the project's scene."""
    # P1-3 migration template (S10) — mutator-pattern variant. NEW vs parts
    # 3-8: the inner _mutate closure (a `latest_project` snapshot under
    # mutate_project's lock) ALSO gets typed iteration, not just the outer
    # function's input. The mutator still WRITES via dict (the
    # mutate_project contract is "latest_project is mutated in-place"),
    # but the .id comparison is typed (scene.id, not scene["id"]). Index
    # parity (latest_typed.scenes[i] ↔ latest_project["scenes"][i]) is
    # preserved by Pydantic's list-field-order semantics. See
    # docs/MIGRATION-PATTERN-pydantic-caller.md for the recipe + part 8
    # (0883201) for the read-only lookup variant of the same index-by-typed-
    # iteration pattern.
    from domain.models import Project as _Project
    from domain.project_manager import MutationResult, mutate_project

    _Project.model_validate(project)  # outer boundary validation

    def _mutate(latest_project: dict):
        latest_typed = _Project.model_validate(latest_project)
        for i, scene in enumerate(latest_typed.scenes):
            if scene.id == scene_id:
                latest_project["scenes"][i]["shots"] = shots
                latest_project["scenes"][i]["num_shots"] = len(shots)
                return True
        return MutationResult(False, save=False)

    mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
