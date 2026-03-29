"""
Cinema Production Tool — Style Director
Repurposed from phase_0_director.py. Takes user's global settings (mood, color palette,
aspect ratio) and produces consistent cinematography, color grading, and sound design rules
that feed into every scene's shot decomposition.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()


def generate_style_rules(
    project_name: str,
    mood: str = "cinematic",
    color_palette: str = "",
    music_mood: str = "suspense",
    aspect_ratio: str = "16:9",
    reference_films: str = "",
    use_web_research: bool = False,
) -> dict:
    """
    Generates consistent style rules for the entire production.

    Args:
        project_name: Film title for context
        mood: Overall emotional tone (melancholic, tense, hopeful, dark, etc.)
        color_palette: User-specified colors (e.g., "warm amber vs cold blue")
        music_mood: Music vibe (suspense, corporate, gritty, cyberpunk, melancholic, uplifting)
        aspect_ratio: Target aspect ratio
        reference_films: Optional film references for style inspiration
        use_web_research: If True, uses Tavily to research aesthetic references (reuses phase_0_director logic)

    Returns:
        Style rules dict with cinematography, color grading, sound design constraints
    """
    import openai

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _default_style_rules(mood, color_palette, music_mood)

    client = openai.OpenAI(api_key=api_key)

    # Research-enhanced context — Tavily + Firecrawl for real cinematography references
    research_context = ""
    try:
        from research_engine import research_cinematography
        # Always search for mood-specific techniques — this grounds the LLM in real cinema
        ref = research_cinematography(mood, "general cinematic setting", f"{mood} film")
        if ref:
            research_context = ref
            print(f"   [STYLE] Research-enhanced with cinematography reference")
    except Exception:
        pass

    # Additional reference film research if specified
    if use_web_research and reference_films:
        film_ref = _research_aesthetic(reference_films)
        if film_ref:
            research_context = f"{research_context}\n{film_ref}" if research_context else film_ref

    system_prompt = f"""You are a world-class cinematographer and production designer.

Create a comprehensive visual style guide for a photorealistic cinema production.

[PROJECT]:
- Title: {project_name}
- Mood: {mood}
- Color Palette Preference: {color_palette or "director's choice based on mood"}
- Music Mood: {music_mood}
- Aspect Ratio: {aspect_ratio}
- Reference Films: {reference_films or "none specified"}
{f'- Research Reference: {research_context[:500]}' if research_context else ''}

{research_context}

Output a JSON object with these exact keys:
- director_vision: The emotional arc and psychological impact of the visual style (2-3 sentences)
- cinematography_rules: Specific camera movement philosophy and framing guidelines
- color_grading_palette: Exact color grading instructions (primary colors, contrast, saturation, highlights, shadows)
- lighting_rules: Lighting philosophy (key light direction, fill ratio, practical lights, color temperature)
- sound_design: Sound design philosophy and ambient texture
- photorealism_rules: Specific instructions for maximum photorealism (skin texture, depth of field, lens choice, film grain)
- composition_rules: Framing and composition guidelines (rule of thirds, leading lines, negative space)

Output ONLY valid JSON."""

    try:
        from web_research import run_with_tools

        system_with_tools = system_prompt + """

IMPORTANT: You have access to web search (tavily_search) and URL scraping (firecrawl_scrape_url).
Use them to research:
- Cinematography styles of reference films
- Color grading techniques used in specific moods/genres
- Professional lighting setups for the target aesthetic
- Real-world photographic techniques for maximum realism
Use tools proactively to make the style guide as professional as possible."""

        raw = run_with_tools(
            client, "gpt-4o",
            system_prompt=system_with_tools,
            user_prompt="Generate the comprehensive style guide. Use web search to research professional cinematography techniques. Output ONLY raw JSON.",
            max_tool_rounds=3,
            response_format={"type": "json_object"},
        )
        rules = json.loads(raw)

        print(f"   ✅ Style rules generated for '{project_name}'")
        return rules

    except Exception as e:
        print(f"   ⚠️ Style generation failed: {e}")
        return _default_style_rules(mood, color_palette, music_mood)


def _default_style_rules(mood: str, color_palette: str, music_mood: str) -> dict:
    """Fallback style rules when GPT-4o is unavailable."""
    mood_palettes = {
        "melancholic": "Desaturated cool tones, blue-grey shadows, warm amber highlights",
        "tense": "High contrast, deep blacks, sharp cold highlights, minimal color",
        "hopeful": "Warm golden tones, soft diffused light, gentle saturation",
        "dark": "Low-key lighting, deep shadows, isolated pools of warm light",
        "cinematic": "Balanced contrast, rich mid-tones, cinematic color science",
    }

    return {
        "director_vision": f"A {mood} visual journey emphasizing photorealistic cinema quality",
        "cinematography_rules": "Smooth deliberate camera movements, motivated by character action. Mix of wide establishing shots and intimate close-ups.",
        "color_grading_palette": color_palette or mood_palettes.get(mood, mood_palettes["cinematic"]),
        "lighting_rules": "Natural motivated lighting with single key source. Fill ratio 1:4 for drama. Color temperature varies by location.",
        "sound_design": f"{music_mood} ambient texture with environmental foley",
        "photorealism_rules": "Visible skin pores with subsurface scattering, shallow depth of field f/1.4-2.8 with circular bokeh, natural film grain ISO 400, micro-detail in fabric weave and material texture, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin, no over-saturated colors",
        "composition_rules": "Rule of thirds, heavy negative space, leading lines toward subject, depth layers (foreground/midground/background)",
    }


def _research_aesthetic(reference_films: str) -> str:
    """Use Tavily to research aesthetic references (reused from phase_0_director logic)."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return ""

    try:
        import requests
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": f"cinematography style analysis {reference_films}",
                "max_results": 3,
            },
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            context_parts = []
            for r in results[:3]:
                context_parts.append(f"- {r.get('title', '')}: {r.get('content', '')[:200]}")
            return f"\n[RESEARCH CONTEXT]:\n" + "\n".join(context_parts)
    except Exception as e:
        print(f"   ⚠️ Tavily research failed: {e}")

    return ""


def _to_str(val) -> str:
    """Safely convert any value to string — handles dicts, lists, etc from GPT-4o."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return ", ".join(f"{k}: {v}" for k, v in val.items())
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def style_rules_to_prompt_suffix(style_rules: dict) -> str:
    """Convert style rules to a prompt suffix injected into every image generation prompt."""
    parts = []
    if style_rules.get("color_grading_palette"):
        parts.append(f"Color grading: {_to_str(style_rules['color_grading_palette'])}")
    if style_rules.get("lighting_rules"):
        parts.append(f"Lighting: {_to_str(style_rules['lighting_rules'])}")
    if style_rules.get("photorealism_rules"):
        parts.append(_to_str(style_rules["photorealism_rules"]))
    if style_rules.get("composition_rules"):
        parts.append(_to_str(style_rules["composition_rules"]))
    return ". ".join(parts)
