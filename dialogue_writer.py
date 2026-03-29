"""
Cinema Production Tool — Dialogue Writer
Auto-generates natural dialogue from action descriptions via GPT-4o.
Outputs editable suggestions that users can accept, modify, or replace.
"""
from typing import Optional, List

import os
import json
from dotenv import load_dotenv

load_dotenv()


def generate_dialogue(
    scene: dict,
    characters: List[dict],
    mood: str = "neutral",
    style: str = "natural, cinematic",
) -> List[dict]:
    """
    Takes a scene's action description and generates dialogue lines
    for each character present.

    Args:
        scene: Scene dict with action, characters_present, mood
        characters: List of character dicts for characters in this scene
        mood: Emotional tone (melancholic, tense, hopeful, etc.)
        style: Dialogue style (natural, cinematic, poetic, etc.)

    Returns:
        List of dialogue line dicts: [{"character_id", "character_name", "text", "delivery"}]
    """
    import openai

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set. Cannot generate dialogue.")
        return []

    client = openai.OpenAI(api_key=api_key)

    char_descriptions = []
    for c in characters:
        char_descriptions.append(
            f"- {c['name']} (ID: {c['id']}): {c.get('description', 'no description')}"
        )

    system_prompt = f"""You are a professional screenwriter for photorealistic cinema.
Write natural, cinematic dialogue for the following scene.

[CHARACTERS]:
{chr(10).join(char_descriptions)}

[RULES]:
1. Dialogue must sound like real people talking — no exposition dumps
2. Each line should be 1-2 sentences max (cinema, not theater)
3. Include delivery notes (whispered, firm, trailing off, etc.)
4. Mood: {mood}
5. Style: {style}
6. If only one character, they can have internal monologue or narration
7. Output ONLY valid JSON array of line objects

JSON Schema per line:
{{"character_id": "char_xxx", "character_name": "Name", "text": "dialogue text", "delivery": "how to deliver"}}"""

    action = scene.get("action", "")
    existing_dialogue = scene.get("dialogue", "")

    user_prompt = f"""Generate dialogue for this scene:

ACTION: {action}
EXISTING DIALOGUE (if any, enhance it): {existing_dialogue if existing_dialogue else 'None — write from scratch'}
MOOD: {mood}

Output ONLY the raw JSON array."""

    try:
        from web_research import run_with_tools

        system_with_tools = system_prompt + """

You have access to web search (tavily_search) and URL scraping (firecrawl_scrape_url).
Use them if you need to research how real people speak in specific contexts,
professional jargon, or cultural speech patterns to make dialogue more authentic.
Only use tools if they would genuinely improve dialogue quality."""

        raw = run_with_tools(
            client, "gpt-4o",
            system_prompt=system_with_tools,
            user_prompt=user_prompt,
            max_tool_rounds=2,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
        # Handle all GPT-4o response shapes:
        # - list: [{line}, {line}]
        # - dict with key: {"lines": [...]} or {"dialogue": [...]}
        # - single dict: {"character_id": ..., "text": ...} (wrap in list)
        if isinstance(parsed, list):
            lines = parsed
        elif isinstance(parsed, dict):
            if "lines" in parsed:
                lines = parsed["lines"]
            elif "dialogue" in parsed:
                lines = parsed["dialogue"]
            elif "dialogue_lines" in parsed:
                lines = parsed["dialogue_lines"]
            elif "text" in parsed:
                # Single line returned as a dict — wrap it
                lines = [parsed]
            else:
                # Try to find any list value in the dict
                lines = []
                for v in parsed.values():
                    if isinstance(v, list):
                        lines = v
                        break
                if not lines:
                    lines = [parsed]  # Last resort: treat the whole dict as one line
        else:
            lines = []

        # Validate
        validated = []
        char_ids = {c["id"] for c in characters}
        for line in lines:
            cid = line.get("character_id", "")
            if cid not in char_ids and characters:
                cid = characters[0]["id"]
            validated.append({
                "character_id": cid,
                "character_name": line.get("character_name", ""),
                "text": line.get("text", ""),
                "delivery": line.get("delivery", "natural"),
            })

        print(f"   ✅ Generated {len(validated)} dialogue lines for scene '{scene.get('title', '')}'")
        return validated

    except Exception as e:
        print(f"   ⚠️ Dialogue generation failed: {e}")
        return []


def format_dialogue_for_voiceover(dialogue_lines: List[dict]) -> List[dict]:
    """
    Formats dialogue lines for the multi-character voiceover system.
    Each line gets the character's voice_id for ElevenLabs TTS.
    """
    formatted = []
    for line in dialogue_lines:
        formatted.append({
            "character_id": line["character_id"],
            "text": line["text"],
            "delivery": line.get("delivery", "natural"),
        })
    return formatted


def dialogue_to_narration_text(dialogue_lines: List[dict]) -> str:
    """Convert dialogue lines to a single narration string for single-voice fallback."""
    parts = []
    for line in dialogue_lines:
        name = line.get("character_name", "")
        text = line.get("text", "")
        if name:
            parts.append(f"{text}")
        else:
            parts.append(text)
    return " ".join(parts)
