"""
LLM prompt optimizer — translates UI creative intent into pipeline-precise prompts.

The big idea: the user types something like "noir detective interrogating suspect
in a rain-streaked room" plus selects mood/characters/location. The pipeline
needs MUCH more — exact cinematography language, per-API prompt shaping, choice
of generation engine, negative constraints, identity anchors. This module is the
glue.

One LLM call produces a structured JSON spec covering:
  - image_prompt: FLUX-shaped prompt with cinematography terms
  - video_prompt: motion/action description for i2v
  - purpose / shot_type: drives routing
  - suggested_image_api / video_api / lipsync_engine: per-purpose recommendation
  - negative_constraints + identity_anchor: quality safety nets
  - camera / lighting / color_palette: cinematography metadata

Falls back to a deterministic template-based optimizer when the LLM isn't
available, so the pipeline keeps moving.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from domain.scene_decomposer import API_REGISTRY, PURPOSE_TAGS, rank_apis_for_purpose


# Whitelist of acceptable purpose values from PURPOSE_TAGS. The LLM hallucinates
# new strings sometimes — we coerce to nearest valid tag.
_VALID_PURPOSES = set(PURPOSE_TAGS)
_VALID_SHOT_TYPES = {"portrait", "medium", "wide", "action", "landscape"}


def _heuristic_purpose_with_objects(
    shot_type: str, has_chars: bool, has_dialogue: bool, has_objects: bool, primary_subject: str,
) -> str:
    """Extended purpose classifier that handles product/object shots.

    primary_subject: 'character' | 'object' | 'environment' — disambiguates when
    both characters and objects are present.
    """
    if has_objects and not has_chars:
        # Pure product shot
        if shot_type == "action":
            return "product_reveal_motion"
        return "product_hero"
    if has_objects and has_chars and primary_subject == "object":
        return "product_in_scene"
    if has_objects and has_chars:
        # Characters lead, product is incidental
        return "product_in_scene" if shot_type in ("portrait", "medium") else "establishing_shot"
    # Fall through to non-object classification
    if not has_chars:
        return "establishing_shot"
    if has_dialogue:
        return "dialogue_close_up" if shot_type in ("portrait", "medium") else "talking_head_full"
    if shot_type == "action":
        return "action_motion"
    if shot_type == "wide":
        return "establishing_shot"
    return "static_portrait"


_OPTIMIZER_SYSTEM_PROMPT = """You are a senior cinema technical director AND commercial product
photographer. You translate creative intent into structured generation specs that an AI
image-and-video pipeline can execute at the highest possible quality.

OUTPUT FORMAT: Strict JSON. No markdown fences, no commentary, no extra fields.

Schema:
{
  "image_prompt":           string,  // FLUX-shaped prompt: subject, action, camera, lens, lighting, mood, quality tags
  "video_prompt":           string,  // motion + dynamic action for image-to-video stage
  "purpose":                string,  // one of: dialogue_close_up | talking_head_full | action_motion | static_portrait | establishing_shot | macro_detail | style_locked_sequence | product_hero | product_in_scene | product_reveal_motion
  "shot_type":              string,  // one of: portrait | medium | wide | action | landscape
  "suggested_image_api":    string,  // FLUX_DEV | HIDREAM_I1 | SD3_5_LARGE
  "suggested_video_api":    string,  // KLING_NATIVE | SORA_NATIVE | VEO_NATIVE | LTX | RUNWAY_GEN4 | AUTO
  "suggested_lipsync":      string,  // HEDRA_C3 | SYNC_SO_V3 | MUSETALK | OMNIHUMAN_V1_5 | LATENTSYNC | null
  "negative_constraints":   string,  // what to avoid: "plastic skin, identity drift, oversaturated, deformed hands, off-brand product, mis-shaped logo"
  "identity_anchor":        string,  // critical visual features to preserve — for objects: brand color, logo, distinctive geometry; for characters: face/hair/build
  "camera":                 string,  // "85mm f/1.4 close-up, shallow DoF, eye-level" or "100mm macro, f/8, ring-flash bounce"
  "lighting":               string,  // "key light from camera-left, warm rim, deep shadows" or "softbox 45°, fill card opposite, hair light"
  "color_palette":          string,  // "amber highlights, deep blue shadows, low-key"
  "reasoning":              string   // 1-2 sentences explaining the picks
}

GUIDELINES (apply rigorously):

1. CINEMATOGRAPHY LANGUAGE. Use real terms: focal length (24mm/50mm/85mm/135mm),
   aperture (f/1.4 - f/8), depth-of-field cue, lighting direction, camera height,
   movement (static, dolly, tracking, crane).

2. PURPOSE → API RECOMMENDATION:
   - dialogue_close_up: video_api=KLING_NATIVE or VEO_NATIVE; lipsync=HEDRA_C3
   - talking_head_full: video_api=VEO_NATIVE; lipsync=HEDRA_C3 or OMNIHUMAN_V1_5
   - action_motion: video_api=SORA_NATIVE; lipsync=null
   - static_portrait: video_api=KLING_NATIVE; lipsync=null
   - establishing_shot: video_api=LTX or VEO_NATIVE; lipsync=null
   - macro_detail: video_api=SORA_NATIVE or LTX; lipsync=null
   - style_locked_sequence: video_api=RUNWAY_GEN4; lipsync per dialogue need

3. NEGATIVE CONSTRAINTS must target common AI failures:
   "plastic skin, frozen face, identity drift, mismatched eyes, deformed hands,
   oversaturated colors, extra fingers, distorted anatomy, blurry face"

4. IDENTITY ANCHOR (only when characters present): one-line description of the
   character's MOST RECOGNIZABLE features. Used to validate every generated shot.

5. SHOT_TYPE follows the geometry of the shot:
   - portrait = close-up/extreme close-up on face
   - medium = waist-up two-shot or one-shot
   - wide = full body or environment with character
   - action = movement-dominated regardless of framing
   - landscape = no characters or characters tiny

6. The image_prompt should READ like a film prompt, not a database schema. Lead
   with the subject and action, then technical cinematography.

7. If the user input is minimal ("a sad woman"), enrich it with sensible defaults
   drawn from the scene mood and palette. Do not invent characters or props that
   weren't requested.

8. LANGUAGE: regardless of the project's dialogue language, the image_prompt
   and video_prompt fields MUST remain in English. FLUX, Sora, Kling, Hedra
   and all other generation engines are trained predominantly on English
   captions — Korean / Japanese / Mandarin prompts produce visibly worse
   output even when the project's dialogue is non-English. The
   identity_anchor, negative_constraints, camera, lighting, color_palette
   fields also stay in English. The dialogue itself is generated separately
   by dialogue_writer in the target language.

9. PRODUCT / OBJECT SHOTS (when objects are present in the OBJECTS IN FRAME list):
   - product_hero: object is THE subject. Use macro/product-photography language:
     "100mm macro lens, f/8 for full sharpness, softbox key + fill card, glossy
     surface highlights, no compression artifacts, hero beauty pass"
   - product_in_scene: object appears with characters. Treat as character shot
     but explicitly position the product and lock its branding.
   - product_reveal_motion: animated reveal/rotation. video_prompt MUST describe
     the motion ("slow 360° rotation revealing brand mark", "lighting transitions
     from dim to spotlight").
   - For metallic/glossy surfaces, request "controlled reflections, no blown
     highlights, dimensional product geometry preserved."
   - For matte surfaces, request "soft directional light, even fall-off, texture
     micro-detail visible."
   - identity_anchor for products MUST cite: brand name, logo placement, distinctive
     color, distinctive shape feature. Example: "Aurora Bottle: cobalt-blue glass,
     gold foil 'Aurora' wordmark centered, tapered neck, embossed bottom seal."
   - negative_constraints for products MUST include: "off-brand colors, deformed
     logo, mis-shaped product silhouette, wrong proportions, plastic-looking
     metallic surface, missing brand mark."
   - For commercial pieces, lean toward HIDREAM_I1 (image) and SORA_NATIVE
     (video reveal) — they preserve product geometry better than the
     character-focused engines.

Output ONLY the JSON. Nothing else."""


def _heuristic_shot_type(user_input: str, has_chars: bool) -> str:
    """Lightweight classifier matching domain.scene_decomposer.classify_shot_type."""
    text = (user_input or "").lower()
    if not has_chars:
        return "landscape"
    if any(k in text for k in ["close-up", "closeup", "close up", "portrait", "ecu", "85mm", "headshot"]):
        return "portrait"
    if any(k in text for k in ["tracking", "running", "chase", "action", "dynamic", "rapid"]):
        return "action"
    if any(k in text for k in ["wide", "establishing", "24mm", "long shot", "full shot"]):
        return "wide"
    return "medium"


def _heuristic_purpose(shot_type: str, has_dialogue: bool) -> str:
    """Map shot_type + dialogue presence to a purpose tag."""
    if shot_type == "landscape":
        return "establishing_shot"
    if has_dialogue:
        return "dialogue_close_up" if shot_type in ("portrait", "medium") else "talking_head_full"
    if shot_type == "action":
        return "action_motion"
    if shot_type == "wide":
        return "establishing_shot"
    return "static_portrait"


def _top_live_api_for_purpose(purpose: str, modality: str) -> str:
    """Pick the highest-ranked live API of a given modality for a purpose."""
    ranked = rank_apis_for_purpose(purpose, status_filter=("live",))
    for key, info in ranked:
        if info.get("modality") == modality:
            return key
    # Fallback to any modality match in the registry
    for key, info in API_REGISTRY.items():
        if info.get("modality") == modality and info.get("status", "live") == "live":
            return key
    return "AUTO"


def _fallback_optimize(
    user_input: str,
    characters: list,
    location: dict,
    global_settings: dict,
    has_dialogue: bool = False,
    objects: Optional[list] = None,
    primary_subject: str = "character",
    intent_notes: str = "",
) -> dict:
    """Deterministic fallback — runs without an LLM. Produces a reasonable spec
    using heuristics + the user's own input as the seed prompt. Lower quality
    than the LLM path but the pipeline doesn't stall."""
    has_chars = bool(characters)
    objects = objects or []
    has_objects = bool(objects)
    shot_type = _heuristic_shot_type(user_input, has_chars or has_objects)
    purpose = _heuristic_purpose_with_objects(
        shot_type, has_chars, has_dialogue, has_objects, primary_subject,
    )

    mood = global_settings.get("music_mood", "cinematic")
    palette = global_settings.get("color_palette", "natural cinematic")
    loc_desc = (location or {}).get("description", "unspecified location")
    loc_light = (location or {}).get("lighting", "natural lighting")

    char_anchor = ""
    if characters:
        traits = characters[0].get("physical_traits") or characters[0].get("description", "")
        char_anchor = f"{characters[0].get('name', 'character')}: {traits[:120]}"

    obj_anchor = ""
    if objects:
        o = objects[0]
        brand = o.get("brand", "")
        material = o.get("material_traits", "")
        texture = o.get("texture_anchor", "")
        parts = [p for p in [o.get("name", ""), brand, material, texture] if p]
        obj_anchor = ": ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else (parts[0] if parts else "")

    identity_anchor = obj_anchor if (has_objects and primary_subject == "object") else char_anchor
    if has_objects and has_chars and primary_subject == "character":
        # Append product anchor as secondary
        identity_anchor = f"{char_anchor}. Product: {obj_anchor}" if char_anchor else obj_anchor

    # Product shots get product-photography prompts
    is_product_shot = purpose in ("product_hero", "product_in_scene", "product_reveal_motion")
    if is_product_shot:
        surface = (objects[0].get("surface_type", "matte") if objects else "matte")
        material = (objects[0].get("material_traits", "") if objects else "")
        camera_str = "100mm macro, f/8 deep focus, eye-level on subject"
        lighting_str = (
            "controlled reflections, softbox key + fill card opposite, hair light for separation"
            if surface in ("glossy", "metallic") else
            "soft directional key 45° camera-left, even fall-off, fill bounce"
        )
        image_prompt = (
            f"Commercial product photography of {user_input.strip().rstrip('.')}. "
            f"{material}. {lighting_str}. "
            f"Sharp focus throughout, no compression artifacts, hero beauty pass, "
            f"premium advertising aesthetic, {palette} palette."
        )
        video_prompt = (
            f"Slow elegant reveal of {user_input.strip()}; smooth camera dolly-in or 180° rotation; "
            f"lighting transitions from low-key to spotlight; product geometry preserved throughout."
        )
        negatives = (
            "off-brand colors, deformed logo, mis-shaped product silhouette, wrong proportions, "
            "plastic-looking metallic surface, missing brand mark, blown highlights, "
            "compressed reflections, asymmetric features, distorted text"
        )
    else:
        camera_str = "85mm f/1.4, shallow DoF, eye-level" if shot_type == "portrait" else "50mm, standard framing"
        lighting_str = loc_light
        intent_prefix = f"Director's intent: {intent_notes.strip()}. " if intent_notes and intent_notes.strip() else ""
        image_prompt = (
            f"{intent_prefix}{user_input.strip().rstrip('.')}. {loc_desc}. {loc_light}. "
            f"{mood} mood, {palette} palette. "
            f"Photorealistic cinematic, 35mm film grain, "
            f"shallow depth of field, professional cinematography."
        )
        video_prompt = f"{user_input.strip()}; subtle natural motion, cinematic camera"
        negatives = (
            "plastic skin, identity drift, deformed hands, mismatched eyes, "
            "oversaturated, extra fingers, distorted anatomy, frozen face, blurry face"
        )

    # Image API: HiDream-I1 if planned + product shot; FLUX-Dev otherwise
    img_api = "FLUX_DEV"
    if is_product_shot:
        # Only use HIDREAM_I1 if it's actually live; else fall to FLUX_DEV
        hidream_status = API_REGISTRY.get("HIDREAM_I1", {}).get("status", "planned")
        if hidream_status == "live":
            img_api = "HIDREAM_I1"

    return {
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
        "purpose": purpose,
        "shot_type": shot_type,
        "suggested_image_api": img_api,
        "suggested_video_api": _top_live_api_for_purpose(purpose, "video"),
        "suggested_lipsync": _top_live_api_for_purpose(purpose, "lipsync") if has_dialogue else None,
        "negative_constraints": negatives,
        "identity_anchor": identity_anchor,
        "camera": camera_str,
        "lighting": lighting_str,
        "color_palette": palette,
        "reasoning": (
            f"fallback (no LLM); purpose={purpose}, "
            f"{'product photography' if is_product_shot else 'cinematic'} mode"
        ),
    }


def _coerce_to_valid_keys(spec: dict, has_chars: bool, has_dialogue: bool) -> dict:
    """Sanitize LLM output — replace invalid enum values with safe defaults."""
    if spec.get("purpose") not in _VALID_PURPOSES:
        spec["purpose"] = _heuristic_purpose(
            spec.get("shot_type", "medium"), has_dialogue,
        )
    if spec.get("shot_type") not in _VALID_SHOT_TYPES:
        spec["shot_type"] = "landscape" if not has_chars else "medium"
    if spec.get("suggested_image_api") not in API_REGISTRY:
        spec["suggested_image_api"] = "FLUX_DEV"
    if spec.get("suggested_video_api") not in API_REGISTRY:
        spec["suggested_video_api"] = "AUTO"
    if has_dialogue:
        if spec.get("suggested_lipsync") not in API_REGISTRY:
            spec["suggested_lipsync"] = _top_live_api_for_purpose(spec["purpose"], "lipsync")
    else:
        spec["suggested_lipsync"] = None
    # Fill missing string fields with empty rather than None to keep downstream simple
    for k in ("image_prompt", "video_prompt", "negative_constraints",
              "identity_anchor", "camera", "lighting", "color_palette", "reasoning"):
        if spec.get(k) is None:
            spec[k] = ""
    return spec


def _strip_json_fences(raw: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` despite instructions."""
    raw = raw.strip()
    if raw.startswith("```"):
        # Drop first and last fence lines
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw


def optimize_shot_prompt(
    user_input: str,
    characters: Optional[list] = None,
    location: Optional[dict] = None,
    global_settings: Optional[dict] = None,
    scene_context: str = "",
    has_dialogue: bool = False,
    objects: Optional[list] = None,
    primary_subject: str = "character",
    intent_notes: str = "",
    ensemble=None,
) -> dict:
    """Translate raw user intent into a structured shot generation spec.

    Args:
        user_input: Raw text the operator typed (shot prompt, intent, or full description).
        characters: List of character dicts (id, name, physical_traits, ...).
        location:   Location dict (description, lighting, time_of_day, weather).
        global_settings: Project-wide settings (music_mood, color_palette, style_rules, ...).
        scene_context:   Optional scene-level description for cross-shot continuity.
        has_dialogue:    True when this shot includes spoken lines.
        objects:         List of product/prop dicts (id, name, brand, material_traits,
                         surface_type, branding_constraints, texture_anchor, ...).
        primary_subject: 'character' | 'object' | 'environment' — disambiguates
                         hero subject when both characters and objects are present.
        intent_notes:    Operator's per-shot creative direction (e.g., "emphasize
                         isolation, cold tones"). Forwarded to the LLM as director's-
                         intent guidance. Empty string (default) leaves existing
                         callers unaffected.
        ensemble:        Optional pre-built LLMEnsemble. If None, builds one or
                         falls back to heuristic path on import failure.

    Returns:
        A dict matching the JSON schema in _OPTIMIZER_SYSTEM_PROMPT. Always
        populated — falls back to heuristic spec on any LLM failure.
    """
    characters = characters or []
    objects = objects or []
    location = location or {}
    global_settings = global_settings or {}
    has_chars = len(characters) > 0

    # Lazy-load the ensemble so this module imports cleanly even if the LLM
    # SDKs are missing.
    if ensemble is None:
        try:
            from llm.ensemble import LLMEnsemble
            ensemble = LLMEnsemble(global_settings)
        except Exception as e:
            print(f"[prompt_optimizer] LLM unavailable ({e}); using fallback path.")
            return _fallback_optimize(
                user_input, characters, location, global_settings,
                has_dialogue, objects=objects, primary_subject=primary_subject,
                intent_notes=intent_notes,
            )

    char_lines = []
    for c in characters[:6]:  # cap to avoid prompt bloat
        traits = c.get("physical_traits") or c.get("description", "")
        char_lines.append(f"- {c.get('name', c.get('id', '?'))}: {traits[:150]}")

    obj_lines = []
    for o in objects[:6]:
        bits = []
        if o.get("brand"): bits.append(f"brand={o['brand']}")
        if o.get("material_traits"): bits.append(f"material={o['material_traits'][:80]}")
        if o.get("surface_type"): bits.append(f"surface={o['surface_type']}")
        if o.get("texture_anchor"): bits.append(f"hero_features={o['texture_anchor'][:80]}")
        if o.get("branding_constraints"): bits.append(f"branding={o['branding_constraints'][:80]}")
        obj_lines.append(f"- {o.get('name', o.get('id', '?'))}: {'; '.join(bits)}")

    project_lang = global_settings.get("language", "English")
    intent_section = (
        f"DIRECTOR'S INTENT FOR THIS SHOT:\n{intent_notes.strip()}\n\n"
        if intent_notes and intent_notes.strip() else ""
    )
    user_prompt = (
        f"USER INTENT:\n{user_input}\n\n"
        f"{intent_section}"
        f"SCENE CONTEXT:\n{scene_context or '(standalone shot)'}\n\n"
        f"CHARACTERS IN FRAME:\n{chr(10).join(char_lines) if char_lines else '(none)'}\n\n"
        f"OBJECTS IN FRAME (products/props):\n{chr(10).join(obj_lines) if obj_lines else '(none)'}\n\n"
        f"PRIMARY SUBJECT: {primary_subject}\n"
        f"LOCATION: {location.get('description', 'unspecified')}\n"
        f"  Lighting: {location.get('lighting', 'natural')}\n"
        f"  Time of day: {location.get('time_of_day', 'day')}\n"
        f"  Weather: {location.get('weather', 'clear')}\n\n"
        f"PROJECT MOOD: {global_settings.get('music_mood', 'cinematic')}\n"
        f"COLOR PALETTE: {global_settings.get('color_palette', 'natural cinematic')}\n"
        f"PROJECT DIALOGUE LANGUAGE: {project_lang} "
        f"(image/video prompts STAY ENGLISH; dialogue is generated separately in {project_lang})\n"
        f"DIALOGUE PRESENT: {'yes' if has_dialogue else 'no'}\n\n"
        f"Produce the JSON shot spec now."
    )

    try:
        result = ensemble.competitive_generate(
            task_type="decompose",
            system_prompt=_OPTIMIZER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=True,
        )
        raw = result.winner_content
        if isinstance(raw, dict):
            spec = raw
        else:
            spec = json.loads(_strip_json_fences(str(raw)))
    except Exception as e:
        print(f"[prompt_optimizer] LLM call failed ({e}); falling back to heuristic.")
        return _fallback_optimize(
            user_input, characters, location, global_settings,
            has_dialogue, objects=objects, primary_subject=primary_subject,
            intent_notes=intent_notes,
        )

    return _coerce_to_valid_keys(spec, has_chars, has_dialogue)


def batch_optimize_scene(
    scene: dict,
    characters: list,
    location: dict,
    global_settings: dict,
    ensemble=None,
) -> list:
    """Run optimize_shot_prompt across every shot in a scene.

    Convenience wrapper for the controller — preserves the scene-level context
    across shots so the LLM sees continuity hints.
    """
    scene_context = (
        f"Scene title: {scene.get('title', 'untitled')}\n"
        f"Action: {scene.get('action', '')[:300]}\n"
        f"Mood: {scene.get('mood', '')}\n"
    )
    out = []
    for shot in scene.get("shots", []):
        dialogue = shot.get("dialogue") or scene.get("dialogue", "")
        has_dialogue = bool(dialogue and dialogue.strip())
        # Limit characters to those actually in frame for this shot
        in_frame_ids = set(shot.get("characters_in_frame", []))
        shot_chars = [c for c in characters if c.get("id") in in_frame_ids] if in_frame_ids else characters
        spec = optimize_shot_prompt(
            user_input=shot.get("prompt", ""),
            characters=shot_chars,
            location=location,
            global_settings=global_settings,
            scene_context=scene_context,
            has_dialogue=has_dialogue,
            ensemble=ensemble,
        )
        out.append({"shot_id": shot.get("id"), "spec": spec})
    return out
