import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
# (Requires GOOGLE_API_KEY environment variable to be set)
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_shorts_script(ctx: dict) -> bool:
    """
    Generates a highly-engaging 60-second YouTube Shorts script directly into the OmniContext.
    Enforces a strict JSON response.
    """
    topic = ctx["topic"]
    language = ctx.get("language", "English")
    print(f"\n✍️ [PHASE A] Writing highly-retentive script in {language.upper()} for topic: {topic}")
    import random
    from phase_e_learning import get_top_performing_context, fetch_live_youtube_trends
    ab_memory = get_top_performing_context()
    live_trends = fetch_live_youtube_trends()
    
    import os
    calibration_matrix = ""
    if os.path.exists("CALIBRATION_MATRIX.txt"):
        with open("CALIBRATION_MATRIX.txt", "r") as f:
            raw_matrix = f.read()
            calibration_matrix = f"\n[🔥 THE OMNI-CALIBRATION MATRIX 🔥]\n{raw_matrix}\n"
    
    styles = [
        "a casual but highly authoritative conversation with an industry expert",
        "an insightful, unscripted breakdown from a trusted advisor",
        "a relaxed, conversational explanation from a leading subject-matter expert",
        "a deep, factual discussion with a knowledgeable mentor"
    ]
    tone = random.choice(styles)
    
    prompt = f"""
    You are an expert YouTube Shorts scriptwriter in the Visual Comfort & Awe niche. 
    
    {calibration_matrix}
    
    {ab_memory}
    
    {live_trends}
    
    Write a highly engaging 35-45 second video script about: "{topic}".
    Use {tone}. Make sure the angle, hook, and body are completely factual, logically sound, and spoken with the confident clarity of an authoritative documentary narrator.
    
    [PROVEN WINNING ANGLES]:
    Your ideal aesthetic is the "Oasis of Awe". Frame everything around "Cosmic Serenity", "Hidden Elegance", or "The Beauty of Mechanics". Make it feel authentically calming and deeply thought-provoking.
    
    [THE GENTLE HOOK ARCHITECTURE (0-3s)]: 
    You MUST gracefully invite the viewer's attention instantly using one of these soothing psychological frameworks:
    - The Peaceful Realization: Gently introduce a profound fact that recontextualizes their day (e.g. "Right now, above you, [Subject] is doing [Gentle Action].")
    - The Micro-Mystery: Warmly invite them to observe something hidden (e.g. "Most people never notice how [Subject] actually [Fascinating Detail].")
    - The Cosmic Perspective: Zoom out immediately to provide emotional relief through scale.
    **CRITICAL 3-SECOND MATRIX CONSTRAINTS**:
    1. CONCRETE ENTITY ANCHORING: Name the specific entity instantly to ground the viewer.
    2. SOOTHING AUDITORY HOOK: The opening sentence must feel like a deep breath. Speak cleanly, warmly, and with a soft, slow, measured cadence. No sudden noises or aggressive claims.
    
    [THE JOURNEY OF AWE (Seconds 3-30)]:
    To sustain gentle attention after the hook, you must execute a "Journey of Awe" sequence that avoids anxiety and builds profound wonder:
    - Phase 1: The Observation (Describe the beautiful reality of the subject using poetic but scientifically accurate terminology).
    - Phase 2: The Deep Dive (Zoom in on the intricate mechanics or zoom out to the cosmic scale. Make the viewer feel a sense of harmony with the universe).
    - Phase 3: The Comforting Resolution (Provide a thoughtful, peaceful conclusion that leaves them feeling calm and enriched).
    
    [ALGORITHMIC ENGAGEMENT - THE REFLECTIVE PAUSE]:
    Instead of polarizing comment-bait, end with a gentle philosophical question that naturally invites viewers to reflect and share their own peaceful thoughts or experiences in the comments. 
    
    [AUTHENTIC, EXPERT CONVERSATION & WORD CHOICE]:
    Flow absolutely naturally, like a wise mentor passing down cosmic secrets by a fireplace. Use natural conversational rhythm with intentional, slow pauses. Speak warmly, softly, and authentically.
    
    [OMNISCIENT RESEARCH & THOUGHT-PROVOKING RESOLUTION]:
    Provide deeply satisfying, elegant facts. The final payoff must provide a calming, unshakeable sense of cosmic trust and wonder.
    
    Rules:
    1. Hook (AUDIO SEO CRITICAL): Start smoothly, gracefully dropping a massive realization with warm authority. You MUST explicitly state the core topic ("{topic}") out loud within the first sentence.
    2. Body: Execute the "Journey of Awe" framework across 3 sequential phases, using strictly conversational and poetic phrasing. Embed SEO keywords naturally.
    3. The Payoff & Action Trigger: Provide a gentle engagement request (e.g., "Take a deep breath, and softly tap subscribe if you felt this.") paired instantly with a relaxing conclusion.
    4. The Infinite Loop & Visual Continuity: You MUST craft the final sentence so it grammatically flows incredibly smoothly back into the first word of the Hook. CRITICAL VISUAL CONTINUITY: The very last AI Image request MUST visually match the framing, lighting, and posture of the very first AI Image request perfectly (e.g. "Frame 12 exactly matches Frame 1").
    5. Length & Vocal Pacing: The script must total EXACTLY 50-65 words. Since you are speaking SOOTHINGLY and SLOWLY, fewer words take up the same 45 seconds. Use punctuation to force ElevenLabs to pause and breathe.
    6. Algorithmic Audio Synchronization: Ensure the exact keywords generated in your `ab_test_titles` and `youtube_tags` are woven naturally into the spoken audio script.
    7. Dual-Model Video Routing (CRITICAL): Assign `target_api` for EVERY visual prompt. 
       - Trigger "RUNWAY" if the scene requires rigid digital structures, geometric data visualization, camera zooms, or minimal physics. 
       - Trigger "VEO" if the scene requires organic fluid dynamics, particle collisions, hyper-macro textures, or natively synchronized ASMR Foley (water, gears, etc.).
    8. The Neural Camera Director: For every single AI Image Prompt, explicitly assign a cinematic camera motion. Focus on extremely smooth, calming motions unless highlighting intense dynamics.
    9. **VISUAL NEGATIVE SPACE**: The AI image prompts MUST explicitly describe scenes with heavily vignette edges, dark or blurred backgrounds, and a highly saturated central subject to perfectly fit the UI without feeling cluttered. The aesthetic is deep, moody, and ultra-high fidelity.
    10. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script, hook, title, and youtube tags are written completely and natively in {language.upper()}. If {language.upper()} is not English, you MUST STILL provide English strings for the image_prompts under `ai_image_prompts` (so the image generator doesn't fail). However, the audio text AND the video title/description MUST heavily prioritize native {language.upper()}.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "ab_test_titles": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "Provide EXACTLY 3 extremely distinct, highly attractive and soothing video titles. Title 1: Gentle curiosity gap. Title 2: Calming realization. Title 3: Peaceful benefit/value. Avoid aggressive clickbait."
            },
            "hook": {"type": "STRING", "description": "The opening gentle, soothing sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "EXACTLY 3 poetic paragraphs mapping directly to the Journey of Awe: [1] Observation, [2] Deep Dive, [3] Comforting Resolution."
            },
            "infinite_loop_bridge": {"type": "STRING", "description": "The serene ending sentence designed to natively reflect back into the hook."},
            "ai_image_prompts": {
                "type": "ARRAY", 
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "The exact Midjourney-style text prompt for the visual. Frame 1 MUST contain high contrast and immediate subject focus. Frame 12 MUST visually match Frame 1 exactly for the seamless loop."},
                        "camera": {
                            "type": "STRING",
                            "enum": ["zoom_in_slow", "zoom_out_slow", "zoom_in_fast", "pan_right", "pan_left", "pan_up_crane", "pan_down", "static_drone", "dolly_in_rapid"],
                            "description": "Select the exact cinematic camera motion that matches the emotional velocity of the spoken audio."
                        },
                        "target_api": {
                            "type": "STRING",
                            "enum": ["VEO", "RUNWAY"],
                            "description": "Select the target video engine. CRITICAL: You MUST forcefully balance the usage! Ensure a 50/50 mixed distribution of 'VEO' and 'RUNWAY' across the 12 clips regardless of the visual content."
                        }
                    },
                    "required": ["prompt", "camera", "target_api"]
                },
                "description": "EXACTLY 12 highly detailed visual prompt objects perfectly tied to the text."
            },
            "youtube_description": {
                "type": "STRING",
                "description": "A deep, comprehensive, and highly-detailed 3-paragraph SEO-optimized YouTube video description. Naturally weave in all logical context, historical facts, and 15 targeted keywords. This must be as exhaustive as possible to maximize YouTube's 5000 character limit for Discovery indexing."
            },
            "youtube_tags": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "EXACTLY 15 highly-targeted, viral YouTube tags relating to the topic."
            },
            "music_vibe": {
                "type": "STRING",
                "enum": ["lofi", "suspense"],
                "description": "Select the emotional vibe. CRITICAL: Use 'lofi' for peaceful, awe-inspiring, or comforting topics to maintain the soothing visual comfort aesthetic. Use 'suspense' ONLY for dark, dangerous, or terrifying cosmic concepts."
            },
            "video_pacing": {
                "type": "STRING",
                "enum": ["relaxed"],
                "description": "Select the pacing. CRITICAL: ALWAYS use 'relaxed' for the new Visual Comfort aesthetic."
            },
            "playlist_category": {
                "type": "STRING",
                "description": "A high-level YouTube playlist name this video belongs to (e.g. 'Cosmic Secrets', 'Tech Mechanics', 'Physics Psychology'). Max 3 words."
            }
        },
        "required": ["ab_test_titles", "hook", "body_paragraphs", "infinite_loop_bridge", "ai_image_prompts", "youtube_description", "youtube_tags", "music_vibe", "video_pacing", "playlist_category"]
    }
    
    # Call the Gemini 2.5 Flash model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.99,
        ),
    )
    
    # Parse and return the JSON string into a Python dictionary
    parsed_json = json.loads(response.text)
    # Inject the randomly selected tone for the experiment logger
    parsed_json['tone_used'] = tone
    
    # NEW: Extract the first A/B title as the master title for system compatibility
    ab_titles = parsed_json.get("ab_test_titles", [])
    if ab_titles and len(ab_titles) > 0:
        parsed_json["title"] = ab_titles[0]
        
        print(f"\n🧪 [A/B TEST TITLES GENERATED FOR YOUTUBE STUDIO]")
        print("Copy/Paste these into the Advanced Features 'Test & Compare' tool tomorrow:")
        for i, t in enumerate(ab_titles):
            print(f"   {i+1}. {t}")
        print("="*60 + "\n")
    else:
        parsed_json["title"] = "Emergency Fallback Title"
    
    ctx["script_data"] = parsed_json
    # Derive core state parameters immediately
    ctx["music_vibe"] = parsed_json.get("music_vibe", "suspense")
    ctx["video_pacing"] = parsed_json.get("video_pacing", "moderate")
    ctx["full_text"] = f"{parsed_json['hook']} {' '.join(parsed_json['body_paragraphs'])} {parsed_json['infinite_loop_bridge']}"
    
    return True

# --- Testing the Module ---
if __name__ == "__main__":
    # A classic, high-performing awe-inspiring topic:
    trending_topic = "How McDonald's actually makes its money from real estate, not selling burgers."
    
    print(f"Generating script for: {trending_topic}\n")
    
    try:
        # Pass a dictionary context as required by generate_shorts_script
        ctx = {"topic": trending_topic}
        generate_shorts_script(ctx)
        print(json.dumps(ctx["script_data"], indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
        print("Make sure you have set the GOOGLE_API_KEY environment variable and installed google-genai.")
