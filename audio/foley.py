"""Foley sound-design generation.

Two providers wired:
  - Stability AI Stable Audio 2 (default, up to 190s)
  - ElevenLabs text-to-sound-effects (22s cap)

Public functions:
  generate_scene_foley         — single SFX (one shot, one sound)
  generate_layered_foley       — 3-layer mix (ambience + action + texture)
  generate_scene_foley_library — iterate all shots, write foley into ctx
  generate_stable_audio_foley  — Stability AI direct REST

The three `_build_*_prompt` helpers (ambience / action / texture) are
pure functions — no external deps, the lowest-coupling code in the module.
The shared ElevenLabs `client` is imported eagerly from `audio._client`.
"""

from __future__ import annotations

import os
from typing import Optional

from audio._client import client


def generate_stable_audio_foley(
    foley_description: str,
    output_filename: str,
    duration: float = 5.0,
    steps: int = 50,
    cfg_scale: float = 7.0,
    seed: Optional[int] = None,
) -> Optional[str]:
    """Generate foley/SFX via Stability AI's Stable Audio 2.0.

    Pros vs ElevenLabs text_to_sound_effects: longer max duration (up to 3 min
    vs ElevenLabs' 22s), better at complex environmental layers (rain on
    metal roof, distant traffic + foreground footsteps), supports audio-to-
    audio remixing on the same endpoint.

    Cons: requires paid Stability AI credits, slightly higher per-clip cost
    than ElevenLabs SFX, no streaming.

    Args:
        foley_description: text prompt for the sound to generate
        output_filename: where to save (audio/mp4 container by default)
        duration: target seconds (Stable Audio supports up to 190s)
        steps: diffusion sampling steps (30-100; 50 is sweet spot)
        cfg_scale: classifier-free guidance (1-10; higher = stricter prompt)
        seed: optional reproducibility seed

    Returns the output path on success, None on failure.
    """
    import requests
    from config.settings import settings

    api_key = settings.stability_api_key
    if not api_key:
        print("   [STABLE-AUDIO] STABILITY_API_KEY not set; skipping")
        return None

    try:
        url = "https://api.stability.ai/v2beta/audio/stable-audio-2/text-to-audio"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "audio/*",
        }
        # Stability uses multipart form for this endpoint
        data = {
            "prompt": foley_description,
            "duration": str(min(int(duration), 190)),
            "steps": str(steps),
            "cfg_scale": str(cfg_scale),
            "output_format": "mp3",
        }
        if seed is not None:
            data["seed"] = str(seed)

        r = requests.post(url, headers=headers, files={k: (None, v) for k, v in data.items()}, timeout=120)
        if r.status_code != 200:
            print(f"   [STABLE-AUDIO] HTTP {r.status_code}: {r.text[:200]}")
            return None
        with open(output_filename, "wb") as f:
            f.write(r.content)
        print(f"   ✅ Stable Audio 2 ({duration}s, cfg={cfg_scale}): {output_filename}")
        return output_filename
    except Exception as e:
        print(f"   [STABLE-AUDIO] failed: {e}")
        return None


def generate_scene_foley(
    foley_description: str,
    output_filename: str,
    duration: float = 5.0,
    provider: Optional[str] = None,
) -> Optional[str]:
    """Generate a single foley sound effect — routed to the configured provider.

    STABLE_AUDIO_FOLEY is preferred for long environmental beds (rain, crowd,
    machinery); ELEVENLABS_V3 is preferred for short specific impacts (glass
    break, footsteps on gravel). Falls back to ElevenLabs on any failure.
    """
    if not provider:
        provider = "ELEVENLABS_V3"

    if provider == "STABLE_AUDIO_FOLEY":
        result = generate_stable_audio_foley(foley_description, output_filename, duration=duration)
        if result:
            return result
        print("   [FOLEY] Stable Audio failed; falling back to ElevenLabs")

    # ElevenLabs default + fallback path
    try:
        result = client.text_to_sound_effects.convert(
            text=foley_description,
            duration_seconds=duration,
            prompt_influence=0.4,
        )
        with open(output_filename, "wb") as f:
            for chunk in result:
                if chunk:
                    f.write(chunk)
        return output_filename
    except Exception as e:
        print(f"   [FOLEY] ElevenLabs fallback failed: {e}")
        return None


def generate_layered_foley(
    shot: dict,
    scene: dict,
    output_filename: str,
    duration: float = 5.0,
) -> Optional[str]:
    """
    Generate multi-layer foley sound design for a shot.

    3 layers mixed together:
    1. AMBIENCE — continuous room tone / environmental background
    2. ACTION — specific sounds matching what's physically happening
    3. TEXTURE — atmospheric detail that fills the sonic space

    Each layer is generated separately via ElevenLabs SFX, then mixed
    via FFmpeg at calibrated volumes (ambience 70%, action 100%, texture 40%).
    """
    import subprocess
    import tempfile

    foley_desc = shot.get("scene_foley", "")
    action = shot.get("action_context", scene.get("action", ""))
    location_desc = scene.get("location_description", "")
    mood = scene.get("mood", "neutral")
    weather = scene.get("weather", "clear")

    # Build targeted prompts for each layer
    ambience_prompt = _build_ambience_prompt(location_desc, weather, mood)
    action_prompt = _build_action_prompt(action, foley_desc)
    texture_prompt = _build_texture_prompt(mood, weather, location_desc)

    print(f"   [FOLEY] Layered sound design: ambience + action + texture")

    # Generate all 3 layers — quality over speed
    temp_dir = tempfile.mkdtemp(prefix="foley_")
    layer_files = []

    for layer_name, prompt in [
        ("ambience", ambience_prompt),
        ("action", action_prompt),
        ("texture", texture_prompt),
    ]:
        layer_path = os.path.join(temp_dir, f"{layer_name}.mp3")
        result = generate_scene_foley(prompt, layer_path, duration=duration)
        if result:
            layer_files.append((layer_name, layer_path))
            print(f"      [FOLEY] {layer_name}: generated")
        else:
            print(f"      [FOLEY] {layer_name}: failed (skipping)")

    if not layer_files:
        # All layers failed — fall back to simple foley
        return generate_scene_foley(foley_desc or "ambient room tone", output_filename, duration)

    # Mix layers with FFmpeg — calibrated volumes per layer
    volume_map = {"ambience": 0.7, "action": 1.0, "texture": 0.4}

    try:
        cmd = ["ffmpeg", "-y"]
        filter_parts = []
        for i, (name, path) in enumerate(layer_files):
            cmd.extend(["-i", path])
            vol = volume_map.get(name, 0.5)
            filter_parts.append(f"[{i}:a]volume={vol}[a{i}]")

        # Mix all layers
        mix_inputs = "".join(f"[a{i}]" for i in range(len(layer_files)))
        filter_parts.append(f"{mix_inputs}amix=inputs={len(layer_files)}:duration=longest:dropout_transition=2[out]")

        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            output_filename,
        ])

        subprocess.run(cmd, capture_output=True, timeout=30)

        # Cleanup temp files
        for _, path in layer_files:
            if os.path.exists(path):
                os.remove(path)

        if os.path.exists(output_filename):
            print(f"   [FOLEY] Mixed {len(layer_files)} layers: {output_filename}")
            return output_filename

    except Exception as e:
        print(f"   [FOLEY] Mix failed: {e}")

    # Fallback: return first successful layer
    if layer_files:
        import shutil
        shutil.copy2(layer_files[0][1], output_filename)
        return output_filename

    return None


def _build_ambience_prompt(location: str, weather: str, mood: str) -> str:
    """Build an ambience prompt from location and weather context."""
    # Location-based ambient sounds
    location_lower = location.lower() if location else ""

    if any(w in location_lower for w in ["park", "garden", "forest", "outdoor", "field"]):
        base = "Birds chirping, gentle breeze through leaves, distant dog barking"
    elif any(w in location_lower for w in ["city", "street", "urban", "downtown"]):
        base = "Distant traffic hum, pedestrian footsteps, car horns far away, city ambience"
    elif any(w in location_lower for w in ["office", "room", "indoor", "apartment", "home"]):
        base = "Quiet room tone, air conditioning hum, distant muffled sounds through walls"
    elif any(w in location_lower for w in ["beach", "ocean", "coast", "shore"]):
        base = "Ocean waves crashing rhythmically, seagulls calling, sand shifting underfoot"
    elif any(w in location_lower for w in ["mountain", "hill", "cliff"]):
        base = "Mountain wind, eagle cry in distance, rocks shifting, vast open space echo"
    elif any(w in location_lower for w in ["cafe", "restaurant", "bar"]):
        base = "Quiet cafe murmur, clinking glasses, espresso machine, soft background chatter"
    else:
        base = f"Ambient room tone, {location}" if location else "Quiet ambient room tone"

    # Weather overlay
    weather_lower = weather.lower() if weather else "clear"
    if "rain" in weather_lower:
        base += ", steady rain falling on surfaces, occasional thunder rumble"
    elif "snow" in weather_lower:
        base += ", muffled snowy silence, wind through bare branches, crunching snow"
    elif "wind" in weather_lower:
        base += ", gusting wind, rustling fabric, swaying branches"
    elif "storm" in weather_lower:
        base += ", heavy storm, thunder cracks, torrential rain, wind howling"

    return base


def _build_action_prompt(action: str, foley_desc: str) -> str:
    """Build an action foley prompt from what the character is doing."""
    if foley_desc:
        return foley_desc

    action_lower = action.lower() if action else ""

    if any(w in action_lower for w in ["walk", "step", "pace"]):
        return "Footsteps on ground, rhythmic walking pace, clothing rustle with movement"
    elif any(w in action_lower for w in ["run", "sprint", "chase"]):
        return "Fast running footsteps, heavy breathing, wind rushing past ears"
    elif any(w in action_lower for w in ["sit", "stand", "lean"]):
        return "Clothing adjustment sounds, chair creak, subtle body movement"
    elif any(w in action_lower for w in ["talk", "speak", "whisper"]):
        return "Subtle lip sounds, breath between words, room presence"
    elif any(w in action_lower for w in ["door", "open", "close", "enter"]):
        return "Door handle turning, door creaking open, footsteps entering room"
    elif any(w in action_lower for w in ["car", "drive", "vehicle"]):
        return "Car engine idling, leather seat movement, turn signal clicking"
    elif any(w in action_lower for w in ["cook", "kitchen", "eat"]):
        return "Sizzling pan, chopping vegetables, running water, plates clinking"
    elif any(w in action_lower for w in ["type", "computer", "work"]):
        return "Keyboard typing, mouse clicking, computer fan hum"
    else:
        return f"Subtle movement sounds, {action}" if action else "Ambient presence, subtle room sounds"


def _build_texture_prompt(mood: str, weather: str, location: str) -> str:
    """Build an atmospheric texture prompt from mood context."""
    mood_lower = mood.lower() if mood else ""

    textures = {
        "melancholic": "Distant piano note reverb, lonely wind, emotional space, minor key drone",
        "tense": "Low frequency rumble, barely perceptible heartbeat, metallic shimmer",
        "dramatic": "Swelling low drone, distant thunder roll, dramatic tension build",
        "mysterious": "Eerie whistle, metallic resonance, unexplained creak, suspense texture",
        "peaceful": "Gentle wind chimes, flowing water stream, birds in distance, warm sunlight feeling",
        "dark": "Deep rumbling bass, metallic scraping far away, industrial undertone",
        "hopeful": "Warm rising tone, gentle shimmer, bright air, morning bird first call",
        "romantic": "Soft vinyl crackle, warm room tone, gentle breathing, intimate closeness",
        "energetic": "Pulsing low frequency, urban hum, electrical buzz, active presence",
    }

    base = textures.get(mood_lower, "Subtle atmospheric drone, cinematic texture, room presence")

    # Weather texture overlay
    if "rain" in (weather or "").lower():
        base += ", rain pattering on window"
    elif "snow" in (weather or "").lower():
        base += ", crystalline silence, muffled world"

    return base


def generate_scene_foley_library(ctx: dict) -> bool:
    """Iterates through each cinematic shot and generates custom ambient Foley layer using ElevenLabs."""
    print("\n🎧 [AUDIO] Generating Immersive Environmental Foley for each scene...")
    prompts = ctx.get("script_data", {}).get("ai_image_prompts", [])
    ctx["foley_audio_paths"] = []

    for i, p in enumerate(prompts):
        foley_desc = p.get("scene_foley", "soft cinematic room tone, faint ambient hum")
        print(f"   ↳ Generating Foley Scene {i+1}: '{foley_desc}'")
        output_filename = f"temp_foley_{i}.mp3"
        try:
            # Generate the sound effect
            result = client.text_to_sound_effects.convert(
                text=foley_desc,
                duration_seconds=5, # Average visual clip length
                prompt_influence=0.4
            )
            with open(output_filename, "wb") as f:
                for chunk in result:
                    if chunk:
                        f.write(chunk)
            ctx["foley_audio_paths"].append(output_filename)
        except Exception as e:
            print(f"      ⚠️ Warning: Foley generation failed for Scene {i+1}: {e}")
            ctx["foley_audio_paths"].append(None) # Safe fallback

    return True
