"""
Cinema Production Tool — Location Manager
Location creation, prompt fragment generation, and per-location seed management
for consistent environments across scenes.
"""

import os
import shutil
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

from project_manager import (
    MutationResult, make_location, add_location, get_project_dir, get_location,
    mutate_project,
)


def _loc_dir(project_id: str, loc_id: str) -> str:
    d = os.path.join(get_project_dir(project_id), "locations", loc_id)
    os.makedirs(d, exist_ok=True)
    return d


def create_location_with_images(
    project: dict,
    name: str,
    description: str,
    reference_image_paths: Optional[List[str]] = None,
    lighting: str = "",
    time_of_day: str = "day",
    weather: str = "clear",
    commit_timeout: float = 10,
) -> dict:
    """
    Creates a location, copies reference images, and generates
    the reusable prompt fragment for injection into all image prompts.
    """
    pid = project["id"]
    location = make_location(
        name=name,
        description=description,
        lighting=lighting,
        time_of_day=time_of_day,
        weather=weather,
    )
    lid = location["id"]
    loc_path = _loc_dir(pid, lid)

    # Copy reference images
    stored_refs = []
    if reference_image_paths:
        for i, src in enumerate(reference_image_paths):
            if os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst = os.path.join(loc_path, f"ref_{i}{ext}")
                shutil.copy2(src, dst)
                stored_refs.append(dst)
                print(f"   📍 Stored location reference: {dst}")

    location["reference_images"] = stored_refs

    # Generate the prompt fragment
    location["prompt_fragment"] = build_location_prompt_fragment(location)

    try:
        add_location(project, location, timeout=commit_timeout)
    except Exception:
        shutil.rmtree(loc_path, ignore_errors=True)
        raise

    print(f"   ✅ Location '{name}' created: {lid}")
    return location


def build_location_prompt_fragment(location: dict) -> str:
    """
    Produces a detailed, reusable prompt string that gets injected verbatim
    into every image generation prompt set at this location.
    Ensures architectural and atmospheric consistency across all shots.
    """
    parts = []

    desc = location.get("description", "").strip()
    if desc:
        parts.append(desc)

    lighting = location.get("lighting", "").strip()
    if lighting:
        parts.append(lighting)
    else:
        tod = location.get("time_of_day", "day")
        lighting_defaults = {
            "dawn": "soft golden hour dawn light filtering through the space",
            "morning": "bright natural morning light with crisp shadows",
            "day": "natural daylight with balanced exposure",
            "afternoon": "warm afternoon light casting long angular shadows",
            "evening": "warm amber evening light with soft ambient glow",
            "night": "moody low-key night lighting with dramatic shadows",
            "golden_hour": "rich golden hour light with warm tones and long shadows",
        }
        parts.append(lighting_defaults.get(tod, "natural lighting"))

    weather = location.get("weather", "").strip()
    if weather and weather != "clear":
        weather_descriptions = {
            "rain": "rain visible through windows, wet reflective surfaces",
            "snow": "snow visible outside, cold blue-white ambient light",
            "fog": "atmospheric fog or haze softening the background",
            "overcast": "soft diffused overcast light with no harsh shadows",
            "storm": "dramatic storm lighting with occasional flashes",
        }
        parts.append(weather_descriptions.get(weather, weather))

    fragment = ", ".join(parts)

    # Wrap in a location anchor for prompt clarity
    location_prompt = f"Setting: {fragment}. Photorealistic, cinematic composition, rule of thirds"
    return location_prompt


def get_location_prompt(project: dict, loc_id: str) -> str:
    """Get the pre-built prompt fragment for a location."""
    loc = get_location(project, loc_id)
    if not loc:
        return ""
    fragment = loc.get("prompt_fragment", "")
    if not fragment:
        def _mutate(latest_project: dict):
            latest_location = get_location(latest_project, loc_id)
            if not latest_location:
                return MutationResult("", save=False)
            latest_fragment = latest_location.get("prompt_fragment", "")
            if latest_fragment:
                return MutationResult(latest_fragment, save=False)
            latest_fragment = build_location_prompt_fragment(latest_location)
            latest_location["prompt_fragment"] = latest_fragment
            return latest_fragment

        fragment = mutate_project(project["id"], _mutate, snapshot=project) or ""
    return fragment


def get_location_seed(project: dict, loc_id: str) -> Optional[int]:
    """Get the deterministic seed for a location (ensures architectural consistency)."""
    loc = get_location(project, loc_id)
    if loc:
        return loc.get("seed")
    return None


def get_location_reference(project: dict, loc_id: str) -> Optional[str]:
    """Get the first available reference image for a location."""
    loc = get_location(project, loc_id)
    if not loc:
        return None
    for ref in loc.get("reference_images", []):
        if os.path.exists(ref):
            return ref
    return None
