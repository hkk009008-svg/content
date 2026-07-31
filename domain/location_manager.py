"""
Cinema Production Tool — Location Manager
Location creation, prompt fragment generation, and per-location seed management
for consistent environments across scenes.
"""

import os
import shutil
import urllib.request
import urllib.error
from typing import Optional, List
from domain.project_manager import (
    MutationResult, make_location, add_location, get_project_dir, get_location,
    mutate_project,
)


def _download_url_to_file(url: str, dst_path: str) -> bool:
    """
    Download *url* to *dst_path*.  Returns True on success, False on any error.
    Never raises — callers must treat False as "skip this URL".
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        with open(dst_path, "wb") as f:
            f.write(data)
        return True
    except Exception as exc:
        print(f"   [RESEARCH] Download failed for {url}: {exc}")
        return False


def _loc_dir(project_id: str, loc_id: str) -> str:
    d = os.path.join(get_project_dir(project_id), "locations", loc_id)
    os.makedirs(d, exist_ok=True)
    return d


def _to_project_relative(project_dir: str, absolute_path: str) -> str:
    """Convert a freshly-written location reference-image path to a
    project-relative form for persistence (Product invariant #6: portable
    persistence -- mirrors slice 10's ``ShotController._to_project_relative``,
    which applies the same invariant to take/shot paths). Location
    reference images are the same class of project-owned output as takes
    and were one of the gaps slice 10's own acceptance criterion left
    uncovered (FIX-REFS).

    Delegates to the ONE implementation via a duck-typed shim exposing only
    ``project_dir`` (the sole attribute that method reads) -- same reuse
    shape as ``_resolve_stored_media_path`` below and
    ``cinema.screening._resolve_manifest_media_path``. This module has no
    controller ``self``, so it can't use ``ReviewController``'s bound-alike
    reuse shape and instead borrows the module-level duck-typed-shim shape.
    Local import keeps ShotController's heavier transitive surface
    (phase_c_vision / lip_sync / etc.) off the location-manager import
    path, and is cycle-safe the same way ``domain.character_manager``'s
    identical helper is (see that module's docstring for the full
    argument): a lazy, call-time import never races the module-load order.
    """
    if not absolute_path:
        return absolute_path
    from cinema.shots.controller import ShotController

    class _PathCtx:
        pass

    ctx = _PathCtx()
    ctx.project_dir = project_dir
    return ShotController._to_project_relative(ctx, absolute_path)


def _resolve_stored_media_path(project: dict, stored_path: str) -> str:
    """Resolve a location reference-image path read back from persisted
    state to a real, directly-openable absolute path under the CURRENT
    project directory. Read-side counterpart to ``_to_project_relative``
    above.

    ``get_location_reference`` must route the raw stored string through
    this before ``os.path.exists`` / opening the file. Without it, a
    project-relative path (this module's current persistence shape) is
    checked against the process CWD instead of the project directory, and a
    legacy absolute path baked in before a repo move silently 404s instead
    of being re-rooted under the current project directory (FIX-REFS).

    Module-level sibling of ``cinema.screening._resolve_manifest_media_path``
    (itself modeled on ``ReviewController._resolve_stored_media_path``):
    this module has no controller ``self`` exposing ``.project`` /
    ``.project_dir``, so it borrows the ONE migration implementation
    (``ShotController._resolve_stored_media_path`` -- relative-join,
    legacy-absolute re-root, never fabricating an escape outside the
    project) via a tiny duck-typed shim carrying the two attributes that
    method reads, instead of copying the migration logic here.
    """
    if not stored_path:
        return stored_path
    project_id = project.get("id") or ""
    if not project_id:
        return stored_path
    from cinema.shots.controller import ShotController

    class _PathCtx:
        pass

    ctx = _PathCtx()
    ctx.project = project
    ctx.project_dir = get_project_dir(project_id)
    return ShotController._resolve_stored_media_path(ctx, stored_path)


def create_location_with_images(
    project: dict,
    name: str,
    description: str,
    reference_image_paths: Optional[List[str]] = None,
    lighting: str = "",
    time_of_day: str = "day",
    weather: str = "clear",
    commit_timeout: float = 10,
    auto_research: bool = False,
) -> dict:
    """
    Creates a location, copies reference images, and generates
    the reusable prompt fragment for injection into all image prompts.

    When *auto_research* is True (default: False), also calls
    ``research_location_visual`` to fetch real photographs of the described
    location via Tavily image search, downloads them locally, and appends
    to ``reference_images``.  This supplements any user-provided uploads.
    If Tavily is unavailable or the download fails for any URL, those refs
    are silently skipped — behaviour is identical to the no-research path.
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
    project_dir = get_project_dir(pid)

    # Copy user-provided reference images
    stored_refs = []
    if reference_image_paths:
        for i, src in enumerate(reference_image_paths):
            if os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst = os.path.join(loc_path, f"ref_{i}{ext}")
                shutil.copy2(src, dst)
                stored_refs.append(dst)
                print(f"   📍 Stored location reference: {dst}")

    # Auto-research: fetch real photos from Tavily and download locally.
    # Supplements uploads — always appends, never replaces.
    if auto_research:
        try:
            from research_engine import research_location_visual
            urls = research_location_visual(description)
        except (ImportError, Exception) as exc:
            print(f"   [RESEARCH] Location visual research unavailable: {exc}")
            urls = []
        base_idx = len(stored_refs)
        for j, url in enumerate(urls):
            ext = ".jpg"
            dst = os.path.join(loc_path, f"ref_research_{base_idx + j}{ext}")
            if _download_url_to_file(url, dst):
                stored_refs.append(dst)
                print(f"   [RESEARCH] Stored researched location ref: {dst}")

    location["reference_images"] = stored_refs

    # Generate the prompt fragment
    location["prompt_fragment"] = build_location_prompt_fragment(location)

    # Persist reference-image paths project-relative (Product invariant #6,
    # FIX-REFS) -- mirrors slice 10's take/shot persistence so an exact repo
    # move doesn't strand the location reference behind a now-stale
    # absolute path. Converted here, after every local absolute-path use
    # above (the copy2/download calls against the real dst files) has
    # already happened.
    location["reference_images"] = [
        _to_project_relative(project_dir, p) for p in location.get("reference_images", [])
    ]

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
        # P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
        # inner mutator-scope validate under the per-project lock. Mixed-shape:
        # typed-helper read (get_location returns dict by id) + raw-dict
        # write (latest_location["prompt_fragment"] = ...). Outer validate
        # skipped: this function is called from many sites that may or may
        # not pass already-validated projects; inner validate alone provides
        # the race-protection guarantee while keeping the caller surface
        # tolerant. See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1"
        # for the canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11
        # c296105).
        from domain.models import Project as _Project

        def _mutate(latest_project: dict):
            _Project.model_validate(latest_project)  # inner mutator-scope validate
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
    # FIX-REFS: resolve through the slice-10 migration chokepoint before
    # checking existence -- see _resolve_stored_media_path's docstring.
    for ref in loc.get("reference_images", []):
        resolved = _resolve_stored_media_path(project, ref)
        if os.path.exists(resolved):
            return resolved
    return None
