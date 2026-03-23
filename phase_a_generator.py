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
    You are an expert YouTube Shorts scriptwriter in the Business & Entrepreneurship niche. 
    
    {calibration_matrix}
    
    {ab_memory}
    
    {live_trends}
    
    Write a highly engaging 35-45 second video script about: "{topic}".
    Use {tone}. Make sure the angle, hook, and body are completely factual, logically sound, and spoken with the confident clarity of an industry expert.
    
    [PROVEN WINNING ANGLES]:
    Your analytics prove that audiences stay engaged when investigating a "Secret", a "Monopoly", or something being "Exposed". Casually frame this topic around one of these angles, but keep it feeling like an authentic, authoritative conversation.
    
    [TRIPARTITE HOOK ARCHITECTURE (0-3s)]: 
    You MUST secure the viewer's attention instantly using one of these strict psychological frameworks:
    - The Contrarian/Pattern Interrupt: Challenge a widely held belief (e.g. "Everything you know about [Subject] is wrong.")
    - The Curiosity Gap: Present an extreme result but withhold the method (e.g. "How [Brand] achieved [Result] without [Expected Method].")
    - In Medias Res (Mid-Action): Bypass all context and begin at the point of maximum tension.
    **CRITICAL 3-SECOND MATRIX CONSTRAINTS**:
    1. CONCRETE ENTITY ANCHORING: Absolutely ban the use of vague pronouns ("This", "That", "The Industry", "The Market") in the first 3 seconds. Name the specific entity (e.g., Amazon, Apple, Boeing) instantly to bypass cognitive load.
    2. AUDITORY HOOK: The opening sentence must pose an incomplete equation or challenge an assumption rather than stating a generic fact. Start instantly without filler.
    The hook must open a cognitive loop (the Zeigarnik effect) that the viewer's brain demands be closed. Do NOT use fake forced TikTok slang like "Dude" or "Yo". Speak cleanly and sharply.
    
    [PAR RETENTION FRAMEWORK (Seconds 3-30)]:
    To sustain >80% APV after the 3-second hook, you must execute a high-velocity Problem-Agitation-Resolution (PAR) sequence to artificially sustain cognitive tension:
    - Phase 1: The Problem (Validate the hook's premise using concrete operational terminology to establish authority).
    - Phase 2: The Agitation (Shift narrative focus to the viewer. Convert the abstract corporate issue into a direct financial/personal offense against the audience. Make them feel the impact).
    - Phase 3: The Resolution & Action Trigger (Provide a partial release of tension built in Phase 2, and guide them into the payoff and call to action).
    
    [ALGORITHMIC ENGAGEMENT FARMING - COMMENT BAIT]:
    To trigger YouTube's comment-ranking algorithm, subtly weave in a highly specific or slightly polarizing statement that naturally invites debate. Make viewers feel smart by giving them a reason to pause the video, go to the comments, and share their own opinion or "correction". 
    
    [AUTHENTIC, EXPERT CONVERSATION & WORD CHOICE]:
    The script must flow absolutely naturally, like you're an expert speaking to a peer or mentee. Use natural conversational rhythm but avoid overly casual slang. If an industry leader wouldn't say it in a relaxed podcast interview, DO NOT USE IT. Avoid formal, written-style narration entirely. Speak directly, confidently, and authentically.
    
    [OMNISCIENT RESEARCH & THOUGHT-PROVOKING RESOLUTION]:
    You must execute profound, deep-level research on the topic. Provide actual numbers, historical context, or complex market dynamics broken down simply. The final payoff must provide a deeply satisfying, logical conclusion that establishes unshakeable trust.
    
    Rules:
    1. Hook (AUDIO SEO CRITICAL): Start mid-conversation (under 3 seconds), casually dropping a massive realization with expert authority. You MUST explicitly state the core topic ("{topic}") out loud within the first sentence for YouTube Audio-SEO indexing.
    2. Body: Execute the Problem-Agitation-Resolution (PAR) framework across 3 sequential phases, using strictly conversational but expert phrasing. Embed SEO keywords naturally.
    3. The Payoff & Action Trigger: Provide a high-friction engagement command (e.g., "Hit subscribe and check the pinned comment") paired instantly with a satisfying, dense conclusion.
    4. The Infinite Loop & Visual Continuity: You MUST craft the final sentence so it grammatically flows backward perfectly into the first word of the Hook to artificially boost Replay metrics >100%. CRITICAL VISUAL CONTINUITY: The very last AI Image request MUST visually match the framing, lighting, and posture of the very first AI Image request perfectly (e.g. "Frame 12 exactly matches Frame 1").
    5. Length & Vocal Pacing: The entire script structure (Hook + PAR Body + Payoff/Loop) must total EXACTLY 75-80 words to maintain a rapid, urgent cadence of ~2.5 words per second. Every sentence must immediately collide into the next without micro-pauses.
    6. Algorithmic Audio Synchronization: YouTube indexes spoken audio. Ensure the exact keywords generated in your `ab_test_titles` and `youtube_tags` are woven naturally into the spoken audio script.
    7. The Neural Camera Director: For every single AI Image Prompt, explicitly assign a cinematic camera motion. Focus on natural, grounded motions unless highlighting something intense.
    8. CRITICAL VISUAL-CAMERA SYNERGY: The physical image prompt MUST mathematically accommodate the camera motion!
    9. **BRIGHT & VIVID VISUALS**: The AI image prompts MUST explicitly describe scenes that are "bright, vividly colored, high-contrast, strictly lit with bright cinematic daylight, high visibility". The visuals must feel crisp and visually bright!
    10. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script, hook, title, and youtube tags are written completely and natively in {language.upper()}. If {language.upper()} is not English, you MUST STILL provide English strings for the image_prompts under `ai_image_prompts` (so the image generator doesn't fail). However, the audio text AND the video title/description MUST heavily prioritize native {language.upper()}.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "ab_test_titles": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "Provide EXACTLY 3 extremely distinct video titles for rigorous algorithmic A/B testing. Title 1: High curiosity gap. Title 2: Aggressive bold claim. Title 3: Pure benefit/value."
            },
            "hook": {"type": "STRING", "description": "The opening sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "EXACTLY 3 punchy paragraphs mapping directly to the PAR Framework: [1] Problem, [2] Agitation, [3] Resolution."
            },
            "infinite_loop_bridge": {"type": "STRING", "description": "The ending sentence designed to natively loop back into the hook."},
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
                        }
                    },
                    "required": ["prompt", "camera"]
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
                "enum": ["suspense", "corporate", "lofi", "upbeat", "aggressive"],
                "description": "Select the emotional vibe. CRITICAL: Do NOT just pick 'lofi' every time! Dynamically change the vibe based strictly on the topic. Use 'suspense' for a cover-up, 'corporate' for financial breakdowns, 'upbeat' for massive success, 'aggressive' for brutal market takeovers, or 'lofi' just for relaxed deep thoughts."
            },
            "video_pacing": {
                "type": "STRING",
                "enum": ["fast", "moderate", "relaxed"],
                "description": "Select the pacing. CRITICAL: Adapt strictly to the vibe of the topic. If it's a fast-paced 'upbeat' or 'aggressive' story, use 'fast'. If it's a 'corporate' or 'suspenseful' mystery, use 'moderate'. If it's a calm 'lofi' reflection, use 'relaxed'."
            },
            "playlist_category": {
                "type": "STRING",
                "description": "A high-level YouTube playlist name this video belongs to (e.g. 'Business Secrets', 'Tech History', 'Marketing Psychology'). Max 3 words."
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
    # A classic, high-performing business case study topic:
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
