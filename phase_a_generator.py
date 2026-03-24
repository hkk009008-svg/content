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
    
    master_storyteller_matrix = {
        "Sagan": {
            "name": "The Sagan Perspective (Cosmic Romanticism)",
            "aesthetic": "Cosmic Romanticism and profound beauty. Emphasize the romantic connection between the viewer and the infinite. Focus on stardust, gentle interconnectedness, and the poetic scale of the cosmos.",
            "hook": "The Peaceful Realization: Gently introduce a beautiful, staggering fact that makes the viewer feel warmly connected to the universe.",
            "pacing": "Flowing, poetic, deeply rhythmic, and highly romantic."
        },
        "Lovecraft": {
            "name": "The Lovecraftian Dread (Cosmic Horror)",
            "aesthetic": "Terrifying cosmic scale and human insignificance. Emphasize the sheer, incomprehensible enormity of reality. Make the viewer feel terribly fragile and microscopic compared to the brutal vastness of nature or space.",
            "hook": "The Staggering Insignificance: Instantly crush their sense of scale with a terrifying, heavy, and haunting realization of how small they are.",
            "pacing": "Slow, brooding, heavy, and ominous."
        },
        "Watts": {
            "name": "The Alan Watts Philosophy (Zen Interconnectedness)",
            "aesthetic": "Zen philosophy, the illusion of separation. Treat the subject as a single breath of the universe. Focus on harmony, paradox, and the beautiful absurdity of human anxiety.",
            "hook": "The Haunting Recontextualization: Dramatically shatter a preconceived notion they hold about reality, revealing that everything is one giant playing mechanism.",
            "pacing": "Warm, philosophical, deeply paradoxical, and unhurried."
        },
        "Orwell": {
            "name": "The Orwellian Mechanic (Brutal Realism)",
            "aesthetic": "Cold, brutal, mechanical reality. Strip away emotion. Focus on harsh, mechanical, and uncompromising truths of nature, physics, or societal structures. It is what it is, and it is beautifully brutal.",
            "hook": "The Cold Truth: Deliver a sharp, unemotional, and undeniably brutal fact. Do not sugarcoat it.",
            "pacing": "Short, sharp, authoritative, and mercilessly logical."
        },
        "Poe": {
            "name": "The Edgar Allan Poe Method (Gothic Suspense)",
            "aesthetic": "Dark, rhythmic, and haunting suspense. Use gothic vocabulary to build a sense of inescapable fate, profound mystery, or deep melancholy.",
            "hook": "The Quiet Immensity: A deeply poetic, softly spoken but terribly haunting realization wrapped in gothic phrasing.",
            "pacing": "Rhythmic, melancholic, very deliberate, and gothic."
        }
    }
    
    lens_key = random.choice(list(master_storyteller_matrix.keys()))
    lens = master_storyteller_matrix[lens_key]
    tone = f"the legendary writing style of {lens['name']}"
    
    prompt = f"""
    You are an elite, award-winning cinematic scriptwriter and documentary narrator.
    
    {calibration_matrix}
    
    {ab_memory}
    
    {live_trends}
    
    Write a highly engaging 35-45 second video script about: "{topic}".
    Write the script exclusively using {tone}. Make sure the angle, hook, and body are completely factual, logically sound, and spoken with the profound, breathtaking gravity of this specific narrative philosophy.
    
    [THE MASTER LENS - {lens['name'].upper()}]:
    Your ideal aesthetic is {lens['aesthetic']}
    
    [THE BREATHTAKING HOOK ARCHITECTURE (0-3s)]: 
    You MUST completely paralyze the viewer's scrolling thumb instantly using this epic psychological framework:
    Hook Mechanism: {lens['hook']}
    **CRITICAL 3-SECOND MATRIX CONSTRAINTS**:
    1. CONCRETE ENTITY ANCHORING: Name the specific entity instantly.
    2. RAW AUDITORY HOOK: The opening sentence must feel like a profound revelation. Speak cleanly, dramatically, and with heavy, deliberate, emotional pauses.
    
    [THE JOURNEY OF AWE (Seconds 3-30)]:
    To sustain breathtaking attention after the hook, you must execute a "Journey of Awe" sequence:
    - Phase 1: The Breathtaking Reality (Describe the intense, epic reality of the subject using highly evocative, cinematic terminology matching your Lens).
    - Phase 2: The Core Mechanic (Zoom in on the microscopic perfection or pull out to the terrifying enormity of the cosmos. Make the viewer feel the true weight of the subject).
    - Phase 3: The Haunting Resolution (Provide a deeply poetic, thought-provoking conclusion that leaves them quite literally breathless and staring at their screen).
    
    [ALGORITHMIC ENGAGEMENT - THE THOUGHT-PROVOKING ELEMENT]:
    Instead of cheap engagement bait, you MUST end the video with a deeply thought-provoking element. Deliver a paradigm-shifting final sentence or a profound, haunting philosophical question that fundamentally alters how the viewer sees their own reality exactly according to your assigned Lens. It should leave them staring at the screen, forcing them to pause, reflect, and organically engage in the comments.
    
    [EPIC NARRATION & WORD CHOICE]:
    Pacing and vocabulary: {lens['pacing']}
    Flow with intense emotional gravity. Use intentional, dramatic pauses. Every single word must carry heavy narrative weight.
    
    [OMNISCIENT RESEARCH & THOUGHT-PROVOKING RESOLUTION]:
    Provide deeply satisfying, elegant, breathtaking facts that invoke true ontological shock and cosmic wonder.
    
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
