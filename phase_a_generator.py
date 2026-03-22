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
    
    [CRITICAL HOOK RULE - FLY UNDER THE RADAR]: 
    Do NOT make the script feel like a staged or overly dramatic TikTok video. Your hook MUST be deeply effective but "fly under the radar". Start as if you're mid-conversation sharing a high-level realization. Use sophisticated yet accessible language. CRITICAL: Do NOT start the script with forced slang like "Dude", "Bro", "Man", or "Yo". Just drop straight into the realization naturally, with undeniable expertise.
    
    [THE OPEN LOOP TRAP - ADDICTIVENESS BOOST]:
    Casually drop a complex question or missing variable early in the script, and unfold the answer logically as if you're mentoring someone, culminating in the final 5 seconds.
    
    [AUTHENTIC, EXPERT CONVERSATION & WORD CHOICE]:
    The script must flow absolutely naturally, like you're an expert speaking to a peer or mentee. Use natural conversational rhythm but avoid overly casual slang. If an industry leader wouldn't say it in a relaxed podcast interview, DO NOT USE IT. Avoid formal, written-style narration entirely. Speak directly, confidently, and authentically.
    
    [OMNISCIENT RESEARCH & THOUGHT-PROVOKING RESOLUTION]:
    You must execute profound, deep-level research on the topic. Provide actual numbers, historical context, or complex market dynamics broken down simply. The final payoff must provide a deeply satisfying, logical conclusion that establishes unshakeable trust.
    
    Rules:
    1. Hook: Start mid-conversation (under 3 seconds), casually dropping a massive realization with expert authority.
    2. Body: Explain the business model or historical strategy casually in 3 clear points, using strictly conversational but expert phrasing.
    3. The Payoff (DENSE & COMPACT): Close the open loop at the very end with a satisfying conclusion in exactly one or two unforgettable, authoritative sentences.
    4. The Infinite Loop CTA: You MUST craft the final sentence of the script so it grammatically and flawlessly flows backward into the very first word of the Hook. Do NOT say 'Subscribe'.
    5. Length & Pacing (CRITICAL RETENTION OPTIMIZATION): You MUST write a 35 to 45 second script. DO NOT EXCEED 45 SECONDS. To achieve this, use 'relaxed' pacing (under 70 words) or tight 'moderate' pacing (~85 words). Do not rush. Let the words breathe like a real conversation.
    6. The Neural Camera Director: For every single AI Image Prompt, explicitly assign a cinematic camera motion. Focus on natural, grounded motions unless highlighting something intense.
    7. CRITICAL VISUAL-CAMERA SYNERGY: The physical image prompt MUST mathematically accommodate the camera motion!
    8. **BRIGHT & VIVID VISUALS**: The AI image prompts MUST explicitly describe scenes that are "bright, vividly colored, high-contrast, strictly lit with bright cinematic daylight, high visibility". The visuals must feel crisp and visually bright!
    9. **CRITICAL OUTPUT LANGUAGE**: Ensure that the script, hook, title, and youtube tags are written completely and natively in {language.upper()}. If {language.upper()} is not English, you MUST STILL provide English strings for the image_prompts under `ai_image_prompts` (so the image generator doesn't fail). However, the audio text AND the video title/description MUST heavily prioritize native {language.upper()}.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "A catchy title for the video"},
            "hook": {"type": "STRING", "description": "The opening sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "3 punchy bullet points"
            },
            "infinite_loop_bridge": {"type": "STRING", "description": "The ending sentence designed to natively loop back into the hook."},
            "ai_image_prompts": {
                "type": "ARRAY", 
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "The exact Midjourney-style text prompt for the visual."},
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
                "description": "An SEO-optimized 3-sentence YouTube video description loaded with keywords."
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
        "required": ["title", "hook", "body_paragraphs", "infinite_loop_bridge", "ai_image_prompts", "youtube_description", "youtube_tags", "music_vibe", "video_pacing", "playlist_category"]
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
        final_script = generate_shorts_script(trending_topic)
        print(json.dumps(final_script, indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
        print("Make sure you have set the GOOGLE_API_KEY environment variable and installed google-genai.")
