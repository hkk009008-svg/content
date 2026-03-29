"""
Cinema Production Tool — Scene Decomposer
Replaces the monolithic 20-prompt auto-generation (phase_a_generator.py) with
per-scene decomposition. Takes user-defined scenes and converts them into
technically precise image generation prompts via GPT-4o.
"""
from typing import Optional, List

import os
import json
from dotenv import load_dotenv

load_dotenv()

# Camera motion options — reused from phase_a_generator.py line 155
CAMERA_MOTIONS = [
    "zoom_in_slow", "zoom_out_slow", "zoom_in_fast",
    "pan_right", "pan_left", "pan_up_crane", "pan_down",
    "static_drone", "dolly_in_rapid",
]

# Visual effects — reused from phase_a_generator.py line 161
VISUAL_EFFECTS = [
    "gritty_contrast", "cinematic_glow", "cyberpunk_glitch",
    "dreamy_blur", "documentary_neutral",
]

# API routing — all available video generation engines (native + FAL proxy)
API_REGISTRY = {
    "AUTO":          {"label": "Auto (Smart Routing)",  "category": "smart",     "description": "Picks best API per shot type automatically"},
    "KLING_NATIVE":  {"label": "Kling 3.0 Native",     "category": "native",    "description": "Best faces — subject binding + face_consistency"},
    "SORA_NATIVE":   {"label": "Sora 2 Native",        "category": "native",    "description": "Best motion physics — body momentum, cloth sim"},
    "VEO_NATIVE":    {"label": "Veo 3.1 Native",       "category": "native",    "description": "Native audio + reference images, 1080p"},
    "RUNWAY_GEN4":   {"label": "Runway Gen-4",         "category": "native",    "description": "Style lock with 3 references, turbo preview"},
    "LTX":           {"label": "LTX Video 2.3",        "category": "native",    "description": "4K, keyframe interpolation, cheapest (~$0.06/s)"},
    "KLING_3_0":     {"label": "Kling (FAL Proxy)",    "category": "fal_proxy", "description": "Kling via FAL — reliable fallback"},
    "SORA_2":        {"label": "Sora 2 (FAL Proxy)",   "category": "fal_proxy", "description": "Sora via FAL — 25s continuous"},
    "VEO":           {"label": "Veo (FAL Proxy)",      "category": "fal_proxy", "description": "Veo via FAL — 4 reference images"},
    "RUNWAY":        {"label": "Runway (FAL Proxy)",   "category": "fal_proxy", "description": "Runway via FAL — legacy fallback"},
}
TARGET_APIS = list(API_REGISTRY.keys())

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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set. Cannot decompose scene.")
        return _fallback_decompose(scene, characters, location)

    client = openai.OpenAI(api_key=api_key)

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
    except Exception:
        pass  # Research is optional — never blocks generation

    # Target shot count based on duration
    duration = scene.get("duration_seconds", 5)
    target_shots = max(2, min(5, int(duration / 2.5)))

    system_prompt = f"""<SYSTEM_PERSONA>
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

<VIDEO_API_EXPERTISE>
You have access to 5 video generation APIs. Choose the BEST one per shot based on shot type:

| Shot Type (from [SHOT] section) | Best API (target_api) | Why |
|---------------------------------|----------------------|-----|
| Close-up / portrait / headshot / 85mm | KLING_NATIVE | Subject binding + face_consistency flag = strongest identity lock |
| Medium / waist-up / 50mm / two-shot | KLING_NATIVE | Good face + scene balance, subject binding available |
| Wide / establishing / 24mm / full shot | LTX | 4K support, camera motion params, cheapest, depth-aware |
| Action / tracking / chase / dynamic / handheld | SORA_NATIVE | Best motion physics, cloth simulation, body momentum |
| Landscape / aerial / drone / panoramic / no character | LTX | 4K, no face needed, lowest cost, best environments |
| Style-locked / consistent visual style needed | RUNWAY_GEN4 | Style lock with reference images |
| Shot-to-shot transition / first+last frame | VEO_NATIVE | Unique first+last frame interpolation |

CAMERA MOTION GUIDANCE per API:
- KLING_NATIVE: Best with zoom_in_slow, dolly_in_rapid (face-focused motions)
- SORA_NATIVE: Best with pan_right, pan_left, tracking shots (dynamic motion)
- LTX: Has 15 native camera_motion params — use for any complex camera move
- VEO_NATIVE: Best with static or slow motions (leverages reference images)
- RUNWAY_GEN4: Best with zoom_in_slow, static_drone (style-lock motions)

COST ORDER (cheapest first): LTX ($) → Kling ($$) → Veo ($$$) → Runway ($$$) → Sora ($$$$)
Use LTX for all landscape/environment shots to save budget for character-critical shots.
</VIDEO_API_EXPERTISE>

Output ONLY a valid JSON array of shot objects. No markdown wrapping. No explanation."""

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
            validated.append({
                "id": f"shot_{i}",
                "prompt": shot.get("prompt", ""),
                "camera": shot.get("camera", "zoom_in_slow") if shot.get("camera") in CAMERA_MOTIONS else "zoom_in_slow",
                "visual_effect": shot.get("visual_effect", "cinematic_glow") if shot.get("visual_effect") in VISUAL_EFFECTS else "cinematic_glow",
                "target_api": shot.get("target_api", "AUTO") if shot.get("target_api") in TARGET_APIS else "AUTO",
                "scene_foley": shot.get("scene_foley", "ambient room tone"),
                "characters_in_frame": shot.get("characters_in_frame", [c["id"] for c in characters]),
                "primary_character": shot.get("characters_in_frame", [c["id"] for c in characters])[0] if shot.get("characters_in_frame") or characters else "",
                "action_context": shot.get("action_context", scene.get("action", "")),
                "generated_image": "",
                "generated_video": "",
            })

        print(f"   ✅ Decomposed scene '{scene.get('title')}' into {len(validated)} shots")
        return validated

    except Exception as e:
        import traceback
        print(f"   [ERROR] GPT-4o decomposition failed: {e}")
        traceback.print_exc()
        return _fallback_decompose(scene, characters, location)


def _fallback_decompose(
    scene: dict,
    characters: List[dict],
    location: dict,
) -> List[dict]:
    """Simple fallback decomposition when GPT-4o is unavailable."""
    char_ids = [c["id"] for c in characters]
    char_descs = ", ".join(c.get("physical_traits", c.get("description", c["name"])) for c in characters)
    loc_desc = location.get("description", "a cinematic location")
    action = scene.get("action", "standing in the scene")

    shots = [
        {
            "id": "shot_0",
            "prompt": f"[SHOT] Establishing wide shot, 24mm lens, deep depth of field, camera at low angle. [SCENE] {loc_desc}, natural ambient lighting. [ACTION] {char_descs}. {action}, facing the camera. [OUTFIT] Current wardrobe. [QUALITY] Photorealistic, visible skin pores and subsurface scattering, natural film grain ISO 400, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin.",
            "camera": "zoom_in_slow",
            "visual_effect": "cinematic_glow",
            "target_api": "AUTO",
            "scene_foley": "ambient environmental sound",
            "characters_in_frame": char_ids,
            "primary_character": char_ids[0] if char_ids else "",
            "action_context": action,
            "generated_image": "",
            "generated_video": "",
        },
        {
            "id": "shot_1",
            "prompt": f"[SHOT] Medium close-up, 85mm f/1.4 lens, shallow depth of field, eye-level camera. [SCENE] {loc_desc}, natural motivated key light from camera-left. [ACTION] {char_descs}. {action}, looking directly at the camera. [OUTFIT] Current wardrobe with visible fabric texture. [QUALITY] Photorealistic, visible skin pores and subsurface scattering, shallow depth of field with circular bokeh, natural film grain ISO 400, no AI artifacts, no smooth plastic skin.",
            "camera": "dolly_in_rapid",
            "visual_effect": "cinematic_glow",
            "target_api": "AUTO",
            "scene_foley": "subtle environmental ambience",
            "characters_in_frame": char_ids[:1],
            "primary_character": char_ids[0] if char_ids else "",
            "action_context": action,
            "generated_image": "",
            "generated_video": "",
        },
    ]

    print(f"   ⚠️ Used fallback decomposition for scene '{scene.get('title')}' → {len(shots)} shots")
    return shots


def update_scene_shots(project: dict, scene_id: str, shots: list[dict]) -> None:
    """Save decomposed shots back into the project's scene."""
    from project_manager import save_project
    for scene in project["scenes"]:
        if scene["id"] == scene_id:
            scene["shots"] = shots
            scene["num_shots"] = len(shots)
            save_project(project)
            return
